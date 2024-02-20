import base64
import json
import logging
import re
import ffmpeg

from datetime import datetime
from getpass import getpass
from dataclasses import dataclass
from shutil import copyfileobj
from xml.etree import ElementTree
from tqdm import tqdm

from utils.models import *
from utils.utils import sanitise_name, silentremove, download_to_temp, create_temp_filename, create_requests_session
from .mqa_identifier_python.mqa_identifier_python.mqa_identifier import MqaIdentifier
from .tidal_api import TidalTvSession, TidalApi, TidalMobileSession, SessionType, TidalError, TidalRequestError

module_information = ModuleInformation(
    service_name='TIDAL',
    module_supported_modes=ModuleModes.download | ModuleModes.credits | ModuleModes.covers | ModuleModes.lyrics,
    login_behaviour=ManualEnum.manual,
    global_settings={
        'tv_atmos_token': '4N3n6Q1x95LL5K7p',
        'tv_atmos_secret': 'oKOXfJW371cX6xaZ0PyhgGNBdNLlBZd4AKKYougMjik=',
        'mobile_atmos_hires_token': 'km8T1xS355y7dd3H',
        'mobile_hires_token': '6BDSRdpK9hqEBTgU',
        'enable_mobile': True,
        'prefer_ac4': False,
        'fix_mqa': True
    },
    # currently too broken to keep it, cover needs to be jpg else crash, problems on termux due to pillow
    # flags=ModuleFlags.needs_cover_resize,
    session_storage_variables=['sessions'],
    netlocation_constant='tidal',
    test_url='https://tidal.com/browse/track/92265335'
)


@dataclass
class AudioTrack:
    codec: CodecEnum
    sample_rate: int
    bitrate: int
    urls: list


class ModuleInterface:
    # noinspection PyTypeChecker
    def __init__(self, module_controller: ModuleController):
        self.cover_size = module_controller.orpheus_options.default_cover_options.resolution
        self.oprinter = module_controller.printer_controller
        self.print = module_controller.printer_controller.oprint
        self.disable_subscription_check = module_controller.orpheus_options.disable_subscription_check
        self.settings = module_controller.module_settings

        # LOW = 96kbit/s AAC, HIGH = 320kbit/s AAC, LOSSLESS = 44.1/16 FLAC, HI_RES <= 48/24 FLAC with MQA
        self.quality_parse = {
            QualityEnum.MINIMUM: 'LOW',
            QualityEnum.LOW: 'LOW',
            QualityEnum.MEDIUM: 'HIGH',
            QualityEnum.HIGH: 'HIGH',
            QualityEnum.LOSSLESS: 'LOSSLESS',
            QualityEnum.HIFI: 'HI_RES'
        }

        # save all the TidalSession objects
        sessions = {}
        self.available_sessions = [SessionType.TV.name, SessionType.MOBILE_DEFAULT.name, SessionType.MOBILE_ATMOS.name]

        # load all saved sessions (TV, Mobile Atmos, Mobile Default)
        saved_sessions = module_controller.temporary_settings_controller.read('sessions')
        if not saved_sessions:
            saved_sessions = {}

        if not self.settings['enable_mobile']:
            self.available_sessions = [SessionType.TV.name]

        while True:
            login_session = None

            def auth_and_save_session(session, session_type):
                session = self.auth_session(session, session_type, login_session)

                # get the dict representation from the TidalSession object and save it into saved_session/loginstorage
                saved_sessions[session_type] = session.get_storage()
                module_controller.temporary_settings_controller.set('sessions', saved_sessions)
                return session

            # ask for login if there are no saved sessions
            if not saved_sessions:
                login_session_type = None
                if len(self.available_sessions) == 1:
                    login_session_type = self.available_sessions[0]
                else:
                    self.print(f'{module_information.service_name}: Choose a login method:')
                    self.print(f'{module_information.service_name}: 1. TV (browser)')
                    self.print(
                        f"{module_information.service_name}: 2. Mobile (username and password, choose TV if this doesn't work)")

                    while not login_session_type:
                        input_str = input(' Login method: ')
                        try:
                            login_session_type = {
                                '1': SessionType.TV.name,
                                'tv': SessionType.TV.name,
                                '2': SessionType.MOBILE_DEFAULT.name,
                                'mobile': SessionType.MOBILE_DEFAULT.name,
                            }[input_str.lower()]
                        except KeyError:
                            self.print(f'{module_information.service_name}: Invalid choice, try again')

                login_session = auth_and_save_session(self.init_session(login_session_type), login_session_type)

            for session_type in self.available_sessions:
                sessions[session_type] = self.init_session(session_type)

                if session_type in saved_sessions:
                    logging.debug(f'{module_information.service_name}: {session_type} session found, loading')

                    # load the dictionary from the temporary_settings_controller inside the TidalSession class
                    sessions[session_type].set_storage(saved_sessions[session_type])
                else:
                    logging.debug(
                        f'{module_information.service_name}: No {session_type} session found, creating new one')
                    sessions[session_type] = auth_and_save_session(sessions[session_type], session_type)

                # always try to refresh session
                if not sessions[session_type].valid():
                    sessions[session_type].refresh()
                    # Save the refreshed session in the temporary settings
                    saved_sessions[session_type] = sessions[session_type].get_storage()
                    module_controller.temporary_settings_controller.set('sessions', saved_sessions)

                # check for a valid subscription
                subscription = self.check_subscription(sessions[session_type].get_subscription())
                if not subscription:
                    confirm = input(' Do you want to relogin? [Y/n]: ')

                    if confirm.upper() == 'N':
                        self.print('Exiting...')
                        exit()

                    # reset saved sessions and loop back to login
                    saved_sessions = {}
                    break

                if not login_session:
                    login_session = sessions[session_type]

            if saved_sessions:
                break

        # only needed for region locked albums where the track is available but force_album_format is used
        self.album_cache = {}

        # load the Tidal session with all saved sessions (TV, Mobile Atmos, Mobile Default)
        self.session: TidalApi = TidalApi(sessions)

    def init_session(self, session_type):
        session = None
        # initialize session with the needed API keys
        if session_type == SessionType.TV.name:
            session = TidalTvSession(self.settings['tv_atmos_token'], self.settings['tv_atmos_secret'])
        elif session_type == SessionType.MOBILE_ATMOS.name:
            session = TidalMobileSession(self.settings['mobile_atmos_hires_token'])
        else:
            session = TidalMobileSession(self.settings['mobile_hires_token'])
        return session

    def auth_session(self, session, session_type, login_session):
        if login_session:
            # refresh tokens can be used with any client id
            # this can be used to switch to any client type from an existing session
            session.refresh_token = login_session.refresh_token
            session.user_id = login_session.user_id
            session.country_code = login_session.country_code
            session.refresh()
        elif session_type == SessionType.TV.name:
            self.print(f'{module_information.service_name}: Creating a TV session')
            session.auth()
        else:
            self.print(f'{module_information.service_name}: Creating a Mobile session')
            self.print(f'{module_information.service_name}: Enter your TIDAL username and password:')
            self.print(f'{module_information.service_name}: (password will not be echoed)')
            username = input(' Username: ')
            password = getpass(' Password: ')
            session.auth(username, password)
            self.print(f'Successfully logged in, using {session_type} token!')

        return session

    def check_subscription(self, subscription: str) -> bool:
        # returns true if "disable_subscription_checks" is enabled or subscription is HIFI (Plus)
        if not self.disable_subscription_check and subscription not in {'HIFI', 'PREMIUM', 'PREMIUM_PLUS'}:
            self.print(f'{module_information.service_name}: Account does not have a HiFi (Plus) subscription, '
                       f'detected subscription: {subscription}')
            return False
        return True

    @staticmethod
    def _generate_artwork_url(cover_id: str, size: int, max_size: int = 1280):
        # not the best idea, but it rounds the self.cover_size to the nearest number in supported_sizes, 1281 is needed
        # for the "uncompressed" cover
        supported_sizes = [80, 160, 320, 480, 640, 1080, 1280, 1281]
        best_size = min(supported_sizes, key=lambda x: abs(x - size))
        # only supports 80x80, 160x160, 320x320, 480x480, 640x640, 1080x1080 and 1280x1280 only for non playlists
        # return "uncompressed" cover if self.cover_resolution > max_size
        image_name = '{0}x{0}.jpg'.format(best_size) if best_size <= max_size else 'origin.jpg'
        return f'https://resources.tidal.com/images/{cover_id.replace("-", "/")}/{image_name}'

    @staticmethod
    def _generate_animated_artwork_url(cover_id: str, size=1280):
        return 'https://resources.tidal.com/videos/{0}/{1}x{1}.mp4'.format(cover_id.replace('-', '/'), size)

    def search(self, query_type: DownloadTypeEnum, query: str, track_info: TrackInfo = None, limit: int = 20):
        if track_info and track_info.tags.isrc:
            results = self.session.get_tracks_by_isrc(track_info.tags.isrc)
        else:
            results = self.session.get_search_data(query, limit=limit)[query_type.name + 's']

        items = []
        for i in results.get('items'):
            duration, name = None, None
            if query_type is DownloadTypeEnum.artist:
                name = i.get('name')
                artists = None
                year = None
            elif query_type is DownloadTypeEnum.playlist:
                if 'name' in i.get('creator'):
                    artists = [i.get('creator').get('name')]
                elif i.get('type') == 'EDITORIAL':
                    artists = [module_information.service_name]
                else:
                    artists = ['Unknown']

                duration = i.get('duration')
                # TODO: Use playlist creation date or lastUpdated?
                year = i.get('created')[:4]
            elif query_type is DownloadTypeEnum.track:
                artists = [j.get('name') for j in i.get('artists')]
                # Getting the year from the album?
                year = i.get('album').get('releaseDate')[:4] if i.get('album').get('releaseDate') else None
                duration = i.get('duration')
            elif query_type is DownloadTypeEnum.album:
                artists = [j.get('name') for j in i.get('artists')]
                duration = i.get('duration')
                year = i.get('releaseDate')[:4]
            else:
                raise Exception('Query type is invalid')

            if query_type is not DownloadTypeEnum.artist:
                name = i.get('title')
                name += f' ({i.get("version")})' if i.get("version") else ''

            additional = None
            if query_type not in {DownloadTypeEnum.artist, DownloadTypeEnum.playlist}:
                if 'DOLBY_ATMOS' in i.get('audioModes'):
                    additional = "Dolby Atmos"
                elif 'SONY_360RA' in i.get('audioModes'):
                    additional = "360 Reality Audio"
                elif i.get('audioQuality') == 'HI_RES':
                    additional = "MQA"
                else:
                    additional = 'HiFi'

            item = SearchResult(
                name=name,
                artists=artists,
                year=year,
                result_id=str(i.get('id')) if query_type is not DownloadTypeEnum.playlist else i.get('uuid'),
                explicit=i.get('explicit'),
                duration=duration,
                additional=[additional] if additional else None
            )

            items.append(item)

        return items

    def get_playlist_info(self, playlist_id: str) -> PlaylistInfo:
        playlist_data = self.session.get_playlist(playlist_id)
        playlist_tracks = self.session.get_playlist_items(playlist_id)

        tracks = [track.get('item').get('id') for track in playlist_tracks.get('items') if track.get('type') == 'track']

        if 'name' in playlist_data.get('creator'):
            creator_name = playlist_data.get('creator').get('name')
        elif playlist_data.get('type') == 'EDITORIAL':
            creator_name = module_information.service_name
        else:
            creator_name = 'Unknown'

        if playlist_data.get('squareImage'):
            cover_url = self._generate_artwork_url(playlist_data['squareImage'], size=self.cover_size, max_size=1080)
            cover_type = ImageFileTypeEnum.jpg
        else:
            # fallback to defaultPlaylistImage
            cover_url = 'https://tidal.com/browse/assets/images/defaultImages/defaultPlaylistImage.png'
            cover_type = ImageFileTypeEnum.png

        return PlaylistInfo(
            name=playlist_data.get('title'),
            creator=creator_name,
            tracks=tracks,
            release_year=playlist_data.get('created')[:4],
            duration=playlist_data.get('duration'),
            creator_id=playlist_data['creator'].get('id'),
            cover_url=cover_url,
            cover_type=cover_type,
            track_extra_kwargs={
                'data': {track.get('item').get('id'): track.get('item') for track in playlist_tracks.get('items')}
            }
        )

    def get_artist_info(self, artist_id: str, get_credited_albums: bool) -> ArtistInfo:
        artist_data = self.session.get_artist(artist_id)

        artist_albums = self.session.get_artist_albums(artist_id).get('items')
        artist_singles = self.session.get_artist_albums_ep_singles(artist_id).get('items')

        # Only works with a mobile session, annoying, never do this again
        credit_albums = []
        if get_credited_albums and SessionType.MOBILE_DEFAULT.name in self.available_sessions:
            self.session.default = SessionType.MOBILE_DEFAULT
            credited_albums_page = self.session.get_page('contributor', params={'artistId': artist_id})

            # This is so retarded
            page_list = credited_albums_page['rows'][-1]['modules'][0].get('pagedList')
            if page_list:
                total_items = page_list['totalNumberOfItems']
                more_items_link = page_list['dataApiPath'][6:]

                # Now fetch all the found total_items
                items = []
                for offset in range(0, total_items // 50 + 1):
                    print(f'Fetching {offset * 50}/{total_items}', end='\r')
                    items += self.session.get_page(more_items_link, params={'limit': 50, 'offset': offset * 50})[
                        'items']

                credit_albums = [item.get('item').get('album') for item in items]
                self.session.default = SessionType.TV

        # use set to filter out duplicate album ids
        albums = {str(album.get('id')) for album in artist_albums + artist_singles + credit_albums}

        return ArtistInfo(
            name=artist_data.get('name'),
            albums=list(albums),
            album_extra_kwargs={'data': {str(album.get('id')): album for album in artist_albums + artist_singles}}
        )

    def get_album_info(self, album_id: str, data=None) -> AlbumInfo:
        # check if album is already in album cache, add it
        if data is None:
            data = {}

        if data.get(album_id):
            album_data = data[album_id]
        elif self.album_cache.get(album_id):
            album_data = self.album_cache[album_id]
        else:
            album_data = self.session.get_album(album_id)

        # get all album tracks with corresponding credits with a limit of 100
        limit = 100
        cache = {'data': {}}
        try:
            tracks_data = self.session.get_album_contributors(album_id, limit=limit)
            total_tracks = tracks_data.get('totalNumberOfItems')

            # round total_tracks to the next 100 and loop over the offset, that's hideous
            for offset in range(limit, ((total_tracks // limit) + 1) * limit, limit):
                # fetch the new album tracks with the given offset
                track_items = self.session.get_album_contributors(album_id, offset=offset, limit=limit)
                # append those tracks to the album_data
                tracks_data['items'] += track_items.get('items')

            # add the track contributors to a new list called 'credits'
            cache = {'data': {}}
            for track in tracks_data.get('items'):
                track.get('item').update({'credits': track.get('credits')})
                cache.get('data')[str(track.get('item').get('id'))] = track.get('item')

            # filter out video clips
            tracks = [str(track['item']['id']) for track in tracks_data.get('items') if track.get('type') == 'track']
        except TidalError:
            tracks = []

        quality = None
        if 'audioModes' in album_data:
            if album_data['audioModes'] == ['DOLBY_ATMOS']:
                quality = 'Dolby Atmos'
            elif album_data['audioModes'] == ['SONY_360RA']:
                quality = '360'
            elif album_data['audioQuality'] == 'HI_RES':
                quality = 'M'

        release_year = None
        if album_data.get('releaseDate'):
            release_year = album_data.get('releaseDate')[:4]
        elif album_data.get('streamStartDate'):
            release_year = album_data.get('streamStartDate')[:4]
        elif album_data.get('copyright'):
            # assume that every copyright includes the year
            release_year = [int(s) for s in album_data.get('copyright').split() if s.isdigit()]
            if len(release_year) > 0:
                release_year = release_year[0]

        if album_data.get('cover'):
            cover_url = self._generate_artwork_url(album_data.get('cover'), size=self.cover_size)
            cover_type = ImageFileTypeEnum.jpg
        else:
            # fallback to defaultAlbumImage
            cover_url = 'https://tidal.com/browse/assets/images/defaultImages/defaultAlbumImage.png'
            cover_type = ImageFileTypeEnum.png

        return AlbumInfo(
            name=album_data.get('title'),
            release_year=release_year,
            explicit=album_data.get('explicit'),
            quality=quality,
            upc=album_data.get('upc'),
            duration=album_data.get('duration'),
            cover_url=cover_url,
            cover_type=cover_type,
            animated_cover_url=self._generate_animated_artwork_url(album_data.get('videoCover')) if album_data.get(
                'videoCover') else None,
            artist=album_data.get('artist').get('name'),
            artist_id=album_data.get('artist').get('id'),
            tracks=tracks,
            track_extra_kwargs=cache
        )

    def get_track_info(self, track_id: str, quality_tier: QualityEnum, codec_options: CodecOptions,
                       data=None) -> TrackInfo:
        if data is None:
            data = {}

        track_data = data[track_id] if track_id in data else self.session.get_track(track_id)

        album_id = str(track_data.get('album').get('id'))
        # check if album is already in album cache, get it
        try:
            album_data = data[album_id] if album_id in data else self.session.get_album(album_id)
        except TidalError as e:
            # if an error occurs, catch it and set the album_data to an empty dict to catch it
            self.print(f'{module_information.service_name}: {e} Trying workaround ...', drop_level=1)
            album_data = track_data.get('album')
            album_data.update({
                'artist': track_data.get('artist'),
                'numberOfVolumes': 1,
                'audioQuality': 'LOSSLESS',
                'audioModes': ['STEREO']
            })

            # add the region locked album to the cache in order to properly use it later (force_album_format)
            self.album_cache = {album_id: album_data}

        media_tags = track_data['mediaMetadata']['tags']
        format = None
        if codec_options.spatial_codecs:
            if 'SONY_360RA' in media_tags:
                format = '360ra'
            elif 'DOLBY_ATMOS' in media_tags:
                if self.settings['prefer_ac4']:
                    format = 'ac4'
                else:
                    format = 'ac3'
        if 'HIRES_LOSSLESS' in media_tags and not format and quality_tier is QualityEnum.HIFI:
            format = 'flac_hires'

        session = {
            'flac_hires': SessionType.MOBILE_DEFAULT,
            '360ra': SessionType.MOBILE_DEFAULT,
            'ac4': SessionType.MOBILE_ATMOS,
            'ac3': SessionType.TV,
            # TV is used whenever possible to avoid MPEG-DASH, which slows downloading
            None: SessionType.TV,
        }[format]

        if not format and 'DOLBY_ATMOS' in media_tags:
            # if atmos is available, we don't use the TV session here because that will get atmos everytime
            # there are no tracks with both 360RA and atmos afaik,
            # so this shouldn't be an issue for now
            session = SessionType.MOBILE_DEFAULT

        if session.name in self.available_sessions:
            self.session.default = session
        else:
            format = None

        # define all default values in case the stream_data is None (region locked)
        audio_track, mqa_file, track_codec, bitrate, download_args, error = None, None, CodecEnum.FLAC, None, None, None

        try:
            stream_data = self.session.get_stream_url(track_id, self.quality_parse[
                quality_tier] if format != 'flac_hires' else 'HI_RES_LOSSLESS')
        except TidalRequestError as e:
            error = e
            # definitely region locked
            if 'Asset is not ready for playback' in str(e):
                error = f'Track [{track_id}] is not available in your region'
            stream_data = None

        if stream_data is not None:
            if stream_data['manifestMimeType'] == 'application/dash+xml':
                manifest = base64.b64decode(stream_data['manifest'])
                audio_track = self.parse_mpd(manifest)[0]  # Only one AudioTrack?
                track_codec = audio_track.codec
            else:
                manifest = json.loads(base64.b64decode(stream_data['manifest']))
                track_codec = CodecEnum['AAC' if 'mp4a' in manifest['codecs'] else manifest['codecs'].upper()]

            if not codec_data[track_codec].spatial:
                if not codec_options.proprietary_codecs and codec_data[track_codec].proprietary:
                    self.print(f'Proprietary codecs are disabled, if you want to download {track_codec.name}, '
                               f'set "proprietary_codecs": true', drop_level=1)
                    stream_data = self.session.get_stream_url(track_id, 'LOSSLESS')

                    if stream_data['manifestMimeType'] == 'application/dash+xml':
                        manifest = base64.b64decode(stream_data['manifest'])
                        audio_track = self.parse_mpd(manifest)[0]  # Only one AudioTrack?
                        track_codec = audio_track.codec
                    else:
                        manifest = json.loads(base64.b64decode(stream_data['manifest']))
                        track_codec = CodecEnum['AAC' if 'mp4a' in manifest['codecs'] else manifest['codecs'].upper()]

            if audio_track:
                download_args = {'audio_track': audio_track}
            else:
                # check if MQA
                if track_codec is CodecEnum.MQA and self.settings['fix_mqa']:
                    # download the first chunk of the flac file to analyze it
                    temp_file_path = self.download_temp_header(manifest['urls'][0])

                    # detect MQA file
                    mqa_file = MqaIdentifier(temp_file_path)

                # add the file to download_args
                download_args = {'file_url': manifest['urls'][0]}

        # https://en.wikipedia.org/wiki/Audio_bit_depth#cite_ref-1
        bit_depth = (24 if stream_data and stream_data['audioQuality'] == 'HI_RES_LOSSLESS' else 16) \
            if track_codec in {CodecEnum.FLAC, CodecEnum.ALAC} else None
        sample_rate = 48 if track_codec in {CodecEnum.EAC3, CodecEnum.MHA1, CodecEnum.AC4} else 44.1

        if stream_data:
            # fallback bitrate
            bitrate = {
                'LOW': 96,
                'HIGH': 320,
                'LOSSLESS': 1411,
                'HI_RES': None,
                'HI_RES_LOSSLESS': None
            }[stream_data['audioQuality']]

            # manually set bitrate for immersive formats
            if stream_data['audioMode'] == 'DOLBY_ATMOS':
                # check if the Dolby Atmos format is E-AC-3 JOC or AC-4
                if track_codec == CodecEnum.EAC3:
                    bitrate = 768
                elif track_codec == CodecEnum.AC4:
                    bitrate = 256
            elif stream_data['audioMode'] == 'SONY_360RA':
                bitrate = 667

        # more precise bitrate tidal uses MPEG-DASH
        if audio_track:
            bitrate = audio_track.bitrate // 1000
            if stream_data['audioQuality'] == 'HI_RES_LOSSLESS':
                sample_rate = audio_track.sample_rate / 1000

        # now set everything for MQA
        if mqa_file is not None and mqa_file.is_mqa:
            bit_depth = mqa_file.bit_depth
            sample_rate = mqa_file.get_original_sample_rate()

        track_name = track_data.get('title')
        track_name += f' ({track_data.get("version")})' if track_data.get("version") else ''

        if track_data['album'].get('cover'):
            cover_url = self._generate_artwork_url(track_data['album'].get('cover'), size=self.cover_size)
        else:
            # fallback to defaultTrackImage, no cover_type flag? Might crash in the future
            cover_url = 'https://tidal.com/browse/assets/images/defaultImages/defaultTrackImage.png'

        track_info = TrackInfo(
            name=track_name,
            album=album_data.get('title'),
            album_id=album_id,
            artists=[a.get('name') for a in track_data.get('artists')],
            artist_id=track_data['artist'].get('id'),
            release_year=track_data.get('streamStartDate')[:4] if track_data.get(
                'streamStartDate') else track_data.get('dateAdded')[:4] if track_data.get('dateAdded') else None,
            bit_depth=bit_depth,
            sample_rate=sample_rate,
            bitrate=bitrate,
            duration=track_data.get('duration'),
            cover_url=cover_url,
            explicit=track_data.get('explicit'),
            tags=self.convert_tags(track_data, album_data, mqa_file),
            codec=track_codec,
            download_extra_kwargs=download_args,
            lyrics_extra_kwargs={'track_data': track_data},
            # check if 'credits' are present (only from get_album_data)
            credits_extra_kwargs={'data': {track_id: track_data['credits']} if 'credits' in track_data else {}}
        )

        if error is not None:
            track_info.error = f'Error: {error}'

        return track_info

    @staticmethod
    def download_temp_header(file_url: str, chunk_size: int = 32768) -> str:
        # create flac temp_location
        temp_location = create_temp_filename() + '.flac'

        # create session and download the file to the temp_location
        r_session = create_requests_session()

        r = r_session.get(file_url, stream=True, verify=False)
        with open(temp_location, 'wb') as f:
            # only download the first chunk_size bytes
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
                    break

        return temp_location

    @staticmethod
    def parse_mpd(xml: bytes) -> list:
        xml = xml.decode('UTF-8')
        # Removes default namespace definition, don't do that!
        xml = re.sub(r'xmlns="[^"]+"', '', xml, count=1)
        root = ElementTree.fromstring(xml)

        # List of AudioTracks
        tracks = []

        for period in root.findall('Period'):
            for adaptation_set in period.findall('AdaptationSet'):
                for rep in adaptation_set.findall('Representation'):
                    # Check if representation is audio
                    content_type = adaptation_set.get('contentType')
                    if content_type != 'audio':
                        raise ValueError('Only supports audio MPDs!')

                    # Codec checks
                    codec = rep.get('codecs').upper()
                    if codec.startswith('MP4A'):
                        codec = 'AAC'

                    # Segment template
                    seg_template = rep.find('SegmentTemplate')
                    # Add init file to track_urls
                    track_urls = [seg_template.get('initialization')]
                    start_number = int(seg_template.get('startNumber') or 1)

                    # https://dashif-documents.azurewebsites.net/Guidelines-TimingModel/master/Guidelines-TimingModel.html#addressing-explicit
                    # Also see example 9
                    seg_timeline = seg_template.find('SegmentTimeline')
                    if seg_timeline is not None:
                        seg_time_list = []
                        cur_time = 0

                        for s in seg_timeline.findall('S'):
                            # Media segments start time
                            if s.get('t'):
                                cur_time = int(s.get('t'))

                            # Segment reference
                            for i in range((int(s.get('r') or 0) + 1)):
                                seg_time_list.append(cur_time)
                                # Add duration to current time
                                cur_time += int(s.get('d'))

                        # Create list with $Number$ indices
                        seg_num_list = list(range(start_number, len(seg_time_list) + start_number))
                        # Replace $Number$ with all the seg_num_list indices
                        track_urls += [seg_template.get('media').replace('$Number$', str(n)) for n in seg_num_list]

                    tracks.append(AudioTrack(
                        codec=CodecEnum[codec],
                        sample_rate=int(rep.get('audioSamplingRate') or 0),
                        bitrate=int(rep.get('bandwidth') or 0),
                        urls=track_urls
                    ))

        return tracks

    def get_track_download(self, file_url: str = None, audio_track: AudioTrack = None) \
            -> TrackDownloadInfo:
        # only file_url or audio_track at a time

        # MHA1, EC-3 or MQA
        if file_url:
            return TrackDownloadInfo(download_type=DownloadEnum.URL, file_url=file_url)

        # MPEG-DASH
        # use the total_file size for a better progress bar? Is it even possible to calculate the total size from MPD?
        try:
            columns = os.get_terminal_size().columns
            if os.name == 'nt':
                bar = tqdm(audio_track.urls, ncols=(columns - self.oprinter.indent_number),
                           bar_format=' ' * self.oprinter.indent_number + '{l_bar}{bar}{r_bar}')
            else:
                raise OSError
        except OSError:
            bar = tqdm(audio_track.urls, bar_format=' ' * self.oprinter.indent_number + '{l_bar}{bar}{r_bar}')

        # download all segments and save the locations inside temp_locations
        temp_locations = []
        for download_url in bar:
            temp_locations.append(download_to_temp(download_url, extension='mp4'))

        # needed for bar indent
        bar.close()

        # concatenated/Merged .mp4 file
        merged_temp_location = create_temp_filename() + '.mp4'
        # actual converted .flac file
        output_location = create_temp_filename() + '.' + codec_data[audio_track.codec].container.name

        # download is finished, merge chunks into 1 file
        with open(merged_temp_location, 'wb') as dest_file:
            for temp_location in temp_locations:
                with open(temp_location, 'rb') as segment_file:
                    copyfileobj(segment_file, dest_file)

        # convert .mp4 back to .flac
        try:
            ffmpeg.input(merged_temp_location, hide_banner=None, y=None).output(output_location, acodec='copy',
                                                                                loglevel='error').run()
            # Remove all files
            silentremove(merged_temp_location)
            for temp_location in temp_locations:
                silentremove(temp_location)
        except:
            self.print('FFmpeg is not installed or working! Using fallback, may have errors')

            # return the MP4 temp file, but tell orpheus to change the container to .m4a (AAC)
            return TrackDownloadInfo(
                download_type=DownloadEnum.TEMP_FILE_PATH,
                temp_file_path=merged_temp_location,
                different_codec=CodecEnum.AAC
            )

        # return the converted flac file now
        return TrackDownloadInfo(
            download_type=DownloadEnum.TEMP_FILE_PATH,
            temp_file_path=output_location,
        )

    def get_track_cover(self, track_id: str, cover_options: CoverOptions, data=None) -> CoverInfo:
        if data is None:
            data = {}

        track_data = data[track_id] if track_id in data else self.session.get_track(track_id)
        cover_id = track_data['album'].get('cover')

        if cover_id:
            return CoverInfo(url=self._generate_artwork_url(cover_id, size=cover_options.resolution),
                             file_type=ImageFileTypeEnum.jpg)

        return CoverInfo(url='https://tidal.com/browse/assets/images/defaultImages/defaultTrackImage.png',
                         file_type=ImageFileTypeEnum.png)

    def get_track_lyrics(self, track_id: str, track_data: dict = None) -> LyricsInfo:
        if not track_data:
            track_data = {}

        # get lyrics data for current track id
        lyrics_data = self.session.get_lyrics(track_id)

        if 'error' in lyrics_data and track_data:
            # search for title and artist to find a matching track (non Atmos)
            results = self.search(
                DownloadTypeEnum.track,
                f'{track_data.get("title")} {" ".join(a.get("name") for a in track_data.get("artists"))}',
                limit=10)

            # check every result to find a matching result
            best_tracks = [r.result_id for r in results
                           if r.name == track_data.get('title') and
                           r.artists[0] == track_data.get('artist').get('name') and
                           'Dolby Atmos' not in r.additional]

            # retrieve the lyrics for the first one, otherwise return empty dict
            lyrics_data = self.session.get_lyrics(best_tracks[0]) if len(best_tracks) > 0 else {}

        embedded = lyrics_data.get('lyrics')
        synced = lyrics_data.get('subtitles')

        return LyricsInfo(
            embedded=embedded,
            # regex to remove the space after the timestamp "[mm:ss.xx] " to "[mm:ss.xx]"
            synced=re.sub(r'(\[\d{2}:\d{2}.\d{2,3}])(?: )', r'\1', synced) if synced else None
        )

    def get_track_credits(self, track_id: str, data=None) -> Optional[list]:
        if data is None:
            data = {}

        credits_dict = {}

        # fetch credits from cache if not fetch those credits
        if track_id in data:
            track_contributors = data[track_id]

            for contributor in track_contributors:
                credits_dict[contributor.get('type')] = [c.get('name') for c in contributor.get('contributors')]
        else:
            track_contributors = self.session.get_track_contributors(track_id).get('items')

            if len(track_contributors) > 0:
                for contributor in track_contributors:
                    # check if the dict contains no list, create one
                    if contributor.get('role') not in credits_dict:
                        credits_dict[contributor.get('role')] = []

                    credits_dict[contributor.get('role')].append(contributor.get('name'))

        if len(credits_dict) > 0:
            # convert the dictionary back to a list of CreditsInfo
            return [CreditsInfo(sanitise_name(k), v) for k, v in credits_dict.items()]
        return None

    @staticmethod
    def convert_tags(track_data: dict, album_data: dict, mqa_file: MqaIdentifier = None) -> Tags:
        track_name = track_data.get('title')
        track_name += f' ({track_data.get("version")})' if track_data.get('version') else ''

        extra_tags = {}
        if mqa_file is not None:
            encoder_time = datetime.now().strftime("%b %d %Y %H:%M:%S")
            extra_tags = {
                'ENCODER': f'MQAEncode v1.1, 2.4.0+0 (278f5dd), E24F1DE5-32F1-4930-8197-24954EB9D6F4, {encoder_time}',
                'MQAENCODER': f'MQAEncode v1.1, 2.4.0+0 (278f5dd), E24F1DE5-32F1-4930-8197-24954EB9D6F4, {encoder_time}',
                'ORIGINALSAMPLERATE': str(mqa_file.original_sample_rate)
            }

        return Tags(
            album_artist=album_data.get('artist').get('name') if 'artist' in album_data else None,
            track_number=track_data.get('trackNumber'),
            total_tracks=album_data.get('numberOfTracks'),
            disc_number=track_data.get('volumeNumber'),
            total_discs=album_data.get('numberOfVolumes'),
            isrc=track_data.get('isrc'),
            upc=album_data.get('upc'),
            release_date=album_data.get('releaseDate'),
            copyright=track_data.get('copyright'),
            replay_gain=track_data.get('replayGain'),
            replay_peak=track_data.get('peak'),
            extra_tags=extra_tags
        )
