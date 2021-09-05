import base64
import json
import logging
import re

from urllib.parse import urlparse

from utils.models import *
from utils.utils import sanitise_name
from .tidal_api import TidalTvSession, TidalApi, TidalAuthError

module_information = ModuleInformation(
    service_name='Tidal',
    module_supported_modes=ModuleModes.download | ModuleModes.credits | ModuleModes.lyrics,
    flags=ModuleFlags.custom_url_parsing,
    global_settings={'client_token': 'aR7gUaTK1ihpXOEP', 'client_secret': 'eVWBEkuL2FCjxgjOkR3yK0RYZEbcrMXRc2l8fU3ZCdE='},
    temporary_settings=['session'],
    netlocation_constant='tidal',
    test_url='https://tidal.com/browse/track/92265335'
)

# LOW = 96kbit/s AAC, HIGH = 320kbit/s AAC, LOSSLESS = 44.1/16 FLAC, HI_RES <= 48/24 FLAC with MQA
QUALITY_PARSER = {
    QualityEnum.LOW: 'LOW',
    QualityEnum.MEDIUM: 'HIGH',
    QualityEnum.HIGH: 'HIGH',
    QualityEnum.LOSSLESS: 'LOSSLESS',
    QualityEnum.HIFI: 'HI_RES'
}


class ModuleInterface:
    def __init__(self, module_controller: ModuleController):
        self.module_controller = module_controller
        settings = module_controller.module_settings

        session: TidalTvSession = module_controller.temporary_settings_controller.read('session')

        if not session:
            logging.debug('Tidal: No session found, creating new one')
            session = TidalTvSession(settings['client_token'], settings['client_secret'])

            module_controller.temporary_settings_controller.set('session', session)

        # Always try to refresh session
        if not session.valid():
            session.refresh()
            # Save the refreshed session in the temporary settings
            module_controller.temporary_settings_controller.set('session', session)

        while True:
            # Check for HiFi subscription
            try:
                session.check_subscription()
                break
            except TidalAuthError as e:
                print(f'{e}')
                confirm = input('Do you want to create a new session? [Y/n]: ')

                if confirm.upper() == 'N':
                    print('Exiting...')
                    exit()

                # Create a new session finally
                session = TidalTvSession(settings['client_token'], settings['client_secret'])
                module_controller.temporary_settings_controller.set('session', session)

        self.session = TidalApi(session)
        # Track cache for credits
        self.track_cache = {}

    @staticmethod
    def generate_artwork_url(album_id, size=1280):
        return 'https://resources.tidal.com/images/{0}/{1}x{1}.jpg'.format(album_id.replace('-', '/'), size)

    @staticmethod
    def custom_url_parse(link: str):
        if link.startswith('http'):
            link = re.sub(r'tidal.com\/.{2}\/store\/', 'tidal.com/', link)
            link = re.sub(r'tidal.com\/store\/', 'tidal.com/', link)
            link = re.sub(r'tidal.com\/browse\/', 'tidal.com/', link)
            url = urlparse(link)
            components = url.path.split('/')

            if not components or len(components) <= 2:
                print('Invalid URL: ' + link)
                exit()
            if len(components) == 5:
                type_ = components[3]
                id_ = components[4]
            else:
                type_ = components[1]
                id_ = components[2]
            return DownloadTypeEnum[type_], id_

    def search(self, query_type: DownloadTypeEnum, query: str, tags: Tags = None, limit: int = 10):
        results = self.session.get_search_data(query)

        items = []
        for i in results[query_type.name + 's']['items']:
            if query_type is DownloadTypeEnum.artist:
                name = i['name']
                artists = None
            elif query_type is DownloadTypeEnum.playlist:
                name = i['title']
                artists = [i['creator']['name']]
            elif query_type is DownloadTypeEnum.track:
                name = i['title']
                artists = [j['name'] for j in i['artists']]
            elif query_type is DownloadTypeEnum.album:
                name = i['title']
                artists = [j['name'] for j in i['artists']]
            else:
                raise Exception('Query type is invalid')

            additional = ''
            if query_type != DownloadTypeEnum.artist:
                if i['audioModes'] == ['DOLBY_ATMOS']:
                    additional = "Dolby Atmos"
                elif i['audioModes'] == ['SONY_360RA']:
                    additional = "360 Reality Audio"
                elif i['audioQuality'] == 'HI_RES':
                    additional = "MQA"
                else:
                    additional = 'HiFi'

            item = SearchResult(
                name=name,
                artists=artists,
                result_id=str(i['id']),
                explicit=bool(i['explicit']) if 'explicit' in i else None,
                additional=[additional]
            )

            items.append(item)

        return items

    def get_track_info(self, track_id: str) -> TrackInfo:
        track_data = self.session.get_track(track_id)

        album_id = str(track_data['album']['id'])
        album_data = self.session.get_album(album_id)

        cover_url = self.generate_artwork_url(track_data['album']['cover'])

        stream_data = self.session.get_stream_url(track_id,
                                                  QUALITY_PARSER[self.module_controller.orpheus_options.quality_tier])

        manifest = json.loads(base64.b64decode(stream_data['manifest']))
        track_codec = CodecEnum['AAC' if 'mp4a' in manifest['codecs'] else manifest['codecs'].upper()]

        # Cache codec options from orpheus settings
        codec_options = self.module_controller.orpheus_options.codec_options

        if not codec_data[track_codec].spatial:
            if not codec_options.proprietary_codecs and codec_data[track_codec].proprietary:
                # TODO: use indents from music_downloader.py
                print(f'\t\tProprietary codecs are disabled, if you want to download {track_codec.name}, '
                      f'set "proprietary_codecs": true')
                stream_data = self.session.get_stream_url(track_id, 'LOSSLESS')

                manifest = json.loads(base64.b64decode(stream_data['manifest']))
                track_codec = CodecEnum['AAC' if 'mp4a' in manifest['codecs'] else manifest['codecs'].upper()]

        track_info = TrackInfo(
            track_name=track_data['title'],
            # track_id=track_id,
            album_id=album_id,
            album_name=album_data['title'],
            artist_name=track_data['artist']['name'],
            artist_id=track_data['artist']['id'],
            # TODO: Get correct bit_depth and sample_rate
            bit_depth=24 if manifest['codecs'] == 'mqa' else 16,
            sample_rate=44.1,
            download_type=DownloadEnum.URL,
            cover_url=cover_url,
            file_url=manifest['urls'][0],
            tags=self.convert_tags(track_data, album_data),
            codec=track_codec
        )

        if not codec_options.spatial_codecs and codec_data[track_codec].spatial:
            track_info.error = 'Spatial codecs are disabled, if you want to download it, set "spatial_codecs": true'

        return track_info

    def get_track_lyrics(self, track_id: str) -> LyricsInfo:
        embedded, synced = None, None

        lyrics_data = self.session.get_lyrics(track_id)

        if 'lyrics' in lyrics_data:
            embedded = lyrics_data['lyrics']

        if 'subtitles' in lyrics_data:
            synced = lyrics_data['subtitles']

        return LyricsInfo(
            embedded=embedded,
            synced=synced
        )

    def get_playlist_info(self, playlist_id: str) -> PlaylistInfo:
        playlist_data = self.session.get_playlist(playlist_id)
        playlist_tracks = self.session.get_playlist_items(playlist_id)

        tracks = [track['item']['id'] for track in playlist_tracks['items'] if track['type'] == 'track']

        if 'name' in playlist_data['creator']:
            creator_name = playlist_data['creator']['name']
        elif playlist_data['creator']['id'] == 0:
            creator_name = 'TIDAL'
        else:
            creator_name = 'Unknown'

        cover_url = self.generate_artwork_url(playlist_data['squareImage'], size=1080)

        playlist_info = PlaylistInfo(
            playlist_name=playlist_data['title'],
            playlist_creator_name=creator_name,
            playlist_creator_id=playlist_data['creator']['id'],
            tracks=tracks,
            cover_url=cover_url
        )

        return playlist_info

    def get_album_info(self, album_id):
        album_data = self.session.get_album(album_id)
        # Get all album tracks with corresponding credits
        tracks_data = self.session.get_album_contributors(album_id)

        tracks = [str(track['item']['id']) for track in tracks_data['items']]

        # Cache all track (+credits) in track_cache
        self.track_cache.update({str(track['item']['id']): track for track in tracks_data['items']})

        album_info = AlbumInfo(
            album_name=album_data['title'],
            artist_name=album_data['artist']['name'],
            artist_id=album_data['artist']['id'],
            tracks=tracks,
        )

        return album_info

    def get_artist_info(self, artist_id: str) -> ArtistInfo:
        artist_data = self.session.get_artist(artist_id)

        artist_albums = self.session.get_artist_albums(artist_id)['items']
        artist_singles = self.session.get_artist_albums_ep_singles(artist_id)['items']

        albums = [str(album['id']) for album in artist_albums + artist_singles]

        artist_info = ArtistInfo(
            artist_name=artist_data['name'],
            albums=albums
        )

        return artist_info

    def get_track_credits(self, track_id: str) -> Optional[list]:
        credits_dict = {}

        # Fetch credits from cache if not fetch those credits
        if track_id in self.track_cache:
            track_contributors = self.track_cache[track_id]['credits']

            for contributor in track_contributors:
                credits_dict[contributor['type']] = [c['name'] for c in contributor['contributors']]
        else:
            track_contributors = self.session.get_track_contributors(track_id)['items']

            if len(track_contributors) > 0:
                for contributor in track_contributors:
                    # Check if the dict contains no list, create one
                    if contributor['role'] not in credits_dict:
                        credits_dict[contributor['role']] = []

                    credits_dict[contributor['role']].append(contributor['name'])

        if len(credits_dict) > 0:
            # Convert the dictionary back to a list of CreditsInfo
            return [CreditsInfo(sanitise_name(k), v) for k, v in credits_dict.items()]
        return None

    @staticmethod
    def convert_tags(track_data: dict, album_data: dict) -> Tags:
        release_year = track_data['streamStartDate'][:4]

        tags = Tags(
            title=track_data['title'],
            album=album_data['title'],
            album_artist=album_data['artist']['name'],
            artist=track_data['artist']['name'],
            track_number=track_data['trackNumber'],
            total_tracks=album_data['numberOfTracks'],
            disc_number=track_data['volumeNumber'],
            total_discs=album_data['numberOfVolumes'],
            date=release_year,
            explicit=track_data['explicit'],
            isrc=track_data['isrc'],
            copyright=track_data['copyright'],
            replay_gain=track_data['replayGain'],
            replay_peak=track_data['peak']
        )

        return tags
