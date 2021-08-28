import base64
import json
import sys
import time
import webbrowser
from datetime import datetime, timedelta

import requests
import urllib3

from utils.utils import create_requests_session

technical_names = {
    'eac3': 'E-AC-3 JOC (Dolby Digital Plus with Dolby Atmos, with 5.1 bed)',
    'mha1': 'MPEG-H 3D Audio (Sony 360 Reality Audio)',
    'ac4': 'AC-4 IMS (Dolby AC-4 with Dolby Atmos immersive stereo)',
    'mqa': 'MQA (Master Quality Authenticated) in FLAC container',
    'flac': 'FLAC (Free Lossless Audio Codec)',
    'alac': 'ALAC (Apple Lossless Audio Codec)',
    'mp4a.40.2': 'AAC 320 (Advanced Audio Coding) with a bitrate of 320kb/s',
    'mp4a.40.5': 'AAC 96 (Advanced Audio Coding) with a bitrate of 96kb/s'
}


class TidalRequestError(Exception):
    def __init__(self, payload):
        sf = '{subStatus}: {userMessage} (HTTP {status})'.format(**payload)
        self.payload = payload
        super(TidalRequestError, self).__init__(sf)


class TidalAuthError(Exception):
    def __init__(self, message):
        super(TidalAuthError, self).__init__(message)


class TidalError(Exception):
    def __init__(self, message):
        self.message = message
        super(TidalError, self).__init__(message)


class TidalApi(object):
    TIDAL_API_BASE = 'https://api.tidal.com/v1/'
    TIDAL_VIDEO_BASE = 'https://api.tidalhifi.com/v1/'
    TIDAL_CLIENT_VERSION = '2.26.1'

    def __init__(self, session):
        self.session = session
        self.s = create_requests_session()

    def _get(self, url, params=None, refresh=False):
        if params is None:
            params = {}
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        params['countryCode'] = self.session.country_code
        if 'limit' not in params:
            params['limit'] = '9999'

        # Catch video for different base
        if url[:5] == 'video':
            resp = self.s.get(
                self.TIDAL_VIDEO_BASE + url,
                headers=self.session.auth_headers(),
                params=params,
                verify=False)
        else:
            resp = self.s.get(
                self.TIDAL_API_BASE + url,
                headers=self.session.auth_headers(),
                params=params,
                verify=False)

        # if the request 401s or 403s, try refreshing the TV/Mobile session in case that helps
        if not refresh and (resp.status_code == 401 or resp.status_code == 403):
            if isinstance(self.session, TidalTvSession):
                self.session.refresh()
                return self._get(url, params, True)

        resp_json = None
        try:
            resp_json = resp.json()
        except:  # some tracks seem to return a JSON with leading whitespace
            try:
                resp_json = json.loads(resp.text.strip())
            except:  # if this doesn't work, the HTTP status probably isn't 200. Are we rate limited?
                pass

        if not resp_json:
            raise TidalError('Response was not valid JSON. HTTP status {}. {}'.format(resp.status_code, resp.text))

        if 'status' in resp_json and resp_json['status'] == 404 and \
                'subStatus' in resp_json and resp_json['subStatus'] == 2001:
            raise TidalError('Error: {}. This might be region-locked.'.format(resp_json['userMessage']))

        # Really hacky way, pls don't copy this ever
        if 'status' in resp_json and resp_json['status'] == 404 and \
                'error' in resp_json and resp_json['error'] == 'Not Found':
            return resp_json

        if 'status' in resp_json and not resp_json['status'] == 200:
            raise TidalRequestError(resp_json)

        return resp_json

    def get_stream_url(self, track_id, quality):

        return self._get('tracks/' + str(track_id) + '/playbackinfopostpaywall', {
            'playbackmode': 'STREAM',
            'assetpresentation': 'FULL',
            'audioquality': quality,
            'prefetch': 'false'
        })

    def get_search_data(self, searchterm):
        return self._get('search',
                         params={'query': str(searchterm), 'offset': 0, 'limit': 20, 'includeContributors': 'true'})

    def get_page(self, pageurl):
        return self._get('pages/' + pageurl, params={'deviceType': 'TV', 'locale': 'en_US', 'mediaFormats': 'SONY_360'})

    def get_playlist_items(self, playlist_id):
        result = self._get('playlists/' + playlist_id + '/items', {
            'offset': 0,
            'limit': 100
        })

        if result['totalNumberOfItems'] <= 100:
            return result

        offset = len(result['items'])
        while True:
            buf = self._get('playlists/' + playlist_id + '/items', {
                'offset': offset,
                'limit': 100
            })
            offset += len(buf['items'])
            result['items'] += buf['items']

            if offset >= result['totalNumberOfItems']:
                break

        return result

    def get_playlist(self, playlist_id):
        return self._get('playlists/' + str(playlist_id))

    def get_album_tracks(self, album_id):
        return self._get('albums/' + str(album_id) + '/tracks')

    def get_track(self, track_id):
        return self._get('tracks/' + str(track_id))

    def get_album(self, album_id):
        return self._get('albums/' + str(album_id))

    def get_video(self, video_id):
        return self._get('videos/' + str(video_id))

    def get_favorite_tracks(self, user_id):
        return self._get('users/' + str(user_id) + '/favorites/tracks')

    def get_track_contributors(self, track_id):
        return self._get('tracks/' + str(track_id) + '/contributors')

    def get_album_contributors(self, album_id):
        return self._get('albums/' + album_id + '/items/credits', params={
            'replace': True,
            'offset': 0,
            'limit': 100,
            'includeContributors': True
        })

    def get_lyrics(self, track_id):
        return self._get('tracks/' + str(track_id) + '/lyrics', params={
            'deviceType': 'TV',
            'locale': 'en_US'
        })

    def get_video_contributors(self, video_id):
        return self._get('videos/' + video_id + '/contributors', params={
            'limit': 50
        })

    def get_video_stream_url(self, video_id):
        return self._get('videos/' + str(video_id) + '/streamurl')

    def get_artist(self, artist_id):
        return self._get('artists/' + str(artist_id))

    def get_artist_albums(self, artist_id):
        return self._get('artists/' + str(artist_id) + '/albums')

    def get_artist_albums_ep_singles(self, artist_id):
        return self._get('artists/' + str(artist_id) + '/albums', params={'filter': 'EPSANDSINGLES'})

    def get_type_from_id(self, id):
        result = None
        try:
            result = self.get_album(id)
            return 'a'
        except TidalError:
            pass
        try:
            result = self.get_artist(id)
            return 'r'
        except TidalError:
            pass
        try:
            result = self.get_track(id)
            return 't'
        except TidalError:
            pass
        try:
            result = self.get_video(id)
            return 'v'
        except TidalError:
            pass

        return result


class SessionFormats:
    def __init__(self, session):
        self.mqa_trackid = '91950969'
        self.dolby_trackid = '131069353'
        self.sony_trackid = '142292058'

        self.quality = ['HI_RES', 'LOSSLESS', 'HIGH', 'LOW']

        self.formats = {
            'eac3': False,
            'mha1': False,
            'ac4': False,
            'mqa': False,
            'flac': False,
            'alac': False,
            'mp4a.40.2': False,
            'mp4a.40.5': False
        }

        try:
            self.check_formats(session)
        except TidalRequestError:
            print('\tERROR: No (HiFi) subscription found!')

    def check_formats(self, session):
        api = TidalApi(session)

        for id in [self.dolby_trackid, self.sony_trackid]:
            playback_info = api.get_stream_url(id, ['LOW'])
            if playback_info['manifestMimeType'] == 'application/dash+xml':
                continue
            manifest_unparsed = base64.b64decode(playback_info['manifest']).decode('UTF-8')
            if 'ContentProtection' not in manifest_unparsed:
                self.formats[json.loads(manifest_unparsed)['codecs']] = True

        for i in range(len(self.quality)):
            playback_info = api.get_stream_url(self.mqa_trackid, [self.quality[i]])
            if playback_info['manifestMimeType'] == 'application/dash+xml':
                continue

            manifest_unparsed = base64.b64decode(playback_info['manifest']).decode('UTF-8')
            if 'ContentProtection' not in manifest_unparsed:
                self.formats[json.loads(manifest_unparsed)['codecs']] = True

    def print_fomats(self):
        table = prettytable.PrettyTable()
        table.field_names = ['Codec', 'Technical name', 'Supported']
        table.align = 'l'
        for format in self.formats:
            table.add_row([format, technical_names[format], self.formats[format]])

        string_table = '\t' + table.__str__().replace('\n', '\n\t')
        print(string_table)
        print('')


class TidalTvSession:
    '''
    Tidal session object based on the mobile Android oauth flow
    '''

    def __init__(self, client_token, client_secret):
        self.TIDAL_AUTH_BASE = 'https://auth.tidal.com/v1/'

        self.username = None
        self.client_id = client_token
        self.client_secret = client_secret

        self.device_code = None
        self.user_code = None

        self.access_token = None
        self.refresh_token = None
        self.expires = None
        self.user_id = None
        self.country_code = None

        self.auth()

    def auth(self):
        s = requests.Session()

        # retrieve csrf token for subsequent request
        r = s.post(self.TIDAL_AUTH_BASE + 'oauth2/device_authorization', data={
            'client_id': self.client_id,
            'scope': 'r_usr w_usr'
        }, verify=False)

        if r.status_code == 400:
            raise TidalAuthError("Authorization failed! Is the clientid/token up to date?")
        elif r.status_code == 200:
            self.device_code = r.json()['deviceCode']
            self.user_code = r.json()['userCode']
            print('Opening https://link.tidal.com/{}, log in or sign up to TIDAL.'.format(self.user_code))
            webbrowser.open('https://link.tidal.com/' + self.user_code, new=2)

        data = {
            'client_id': self.client_id,
            'device_code': self.device_code,
            'client_secret': self.client_secret,
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
            'scope': 'r_usr w_usr'
        }

        status_code = 400
        print('Checking link ', end='')

        while status_code == 400:
            for index, char in enumerate("." * 5):
                sys.stdout.write(char)
                sys.stdout.flush()
                # exchange access code for oauth token
                time.sleep(0.2)
            r = requests.post(self.TIDAL_AUTH_BASE + 'oauth2/token', data=data, verify=False)
            status_code = r.status_code
            index += 1  # lists are zero indexed, we need to increase by one for the accurate count
            # backtrack the written characters, overwrite them with space, backtrack again:
            sys.stdout.write("\b" * index + " " * index + "\b" * index)
            sys.stdout.flush()

        if r.status_code == 200:
            print('\nSuccessfully linked!')
        elif r.status_code == 401:
            raise TidalAuthError('Auth Error: ' + r.json()['error'])

        self.access_token = r.json()['access_token']
        self.refresh_token = r.json()['refresh_token']
        self.expires = datetime.now() + timedelta(seconds=r.json()['expires_in'])

        r = requests.get('https://api.tidal.com/v1/sessions', headers=self.auth_headers(), verify=False)
        assert (r.status_code == 200)
        self.user_id = r.json()['userId']
        self.country_code = r.json()['countryCode']

        r = requests.get('https://api.tidal.com/v1/users/{}?countryCode={}'.format(self.user_id, self.country_code),
                         headers=self.auth_headers(), verify=False)
        assert (r.status_code == 200)
        self.username = r.json()['username']

    def check_subscription(self):
        if self.access_token is not None:
            r = requests.get('https://api.tidal.com/v1/users/' + str(self.user_id) + '/subscription',
                             headers=self.auth_headers(), verify=False)
            assert (r.status_code == 200)
            if r.json()['subscription']['type'] not in ['HIFI', 'PREMIUM_PLUS']:
                raise TidalAuthError('You need a HiFi subscription!')

    def valid(self):
        if self.access_token is None or datetime.now() > self.expires:
            return False
        r = requests.get('https://api.tidal.com/v1/sessions', headers=self.auth_headers(), verify=False)
        return r.status_code == 200

    def refresh(self):
        assert (self.refresh_token is not None)
        r = requests.post(self.TIDAL_AUTH_BASE + 'oauth2/token', data={
            'refresh_token': self.refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'refresh_token'
        }, verify=False)

        if r.status_code == 200:
            print('Tidal: Refreshing token successful')
            self.access_token = r.json()['access_token']
            self.expires = datetime.now() + timedelta(seconds=r.json()['expires_in'])

            if 'refresh_token' in r.json():
                self.refresh_token = r.json()['refresh_token']

        return r.status_code == 200

    @staticmethod
    def session_type():
        return 'Tv'

    def auth_headers(self):
        return {
            'Host': 'api.tidal.com',
            'X-Tidal-Token': self.client_id,
            'Authorization': 'Bearer {}'.format(self.access_token),
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip',
            'User-Agent': 'TIDAL_ANDROID/1039 okhttp/3.14.9'
        }
