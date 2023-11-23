import base64
import hashlib
import json
import secrets
import sys
import time
import webbrowser
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto

import requests
import urllib3

import urllib.parse as urlparse
from urllib.parse import parse_qs, quote
from datetime import datetime, timedelta

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


class SessionType(Enum):
    TV = auto()
    MOBILE_ATMOS = auto()
    MOBILE_DEFAULT = auto()


class TidalApi(object):
    TIDAL_API_BASE = 'https://api.tidal.com/v1/'
    TIDAL_VIDEO_BASE = 'https://api.tidalhifi.com/v1/'
    TIDAL_CLIENT_VERSION = '2.26.1'

    def __init__(self, sessions: dict):
        self.sessions = sessions
        self.default: SessionType = SessionType.TV  # Change to TV or MOBILE depending on AC-4/360RA

        self.s = create_requests_session()

    def _get(self, url, params=None, refresh=False):
        if params is None:
            params = {}
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        params['countryCode'] = self.sessions[self.default.name].country_code
        if 'limit' not in params:
            params['limit'] = '9999'

        resp = self.s.get(
            self.TIDAL_API_BASE + url,
            headers=self.sessions[self.default.name].auth_headers(),
            params=params)

        # if the request 401s or 403s, try refreshing the TV/Mobile session in case that helps
        if not refresh and (resp.status_code == 401 or resp.status_code == 403):
            self.sessions[self.default.name].refresh()
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
        return self._get('tracks/' + str(track_id) + '/playbackinfopostpaywall/v4', {
            'playbackmode': 'STREAM',
            'assetpresentation': 'FULL',
            'audioquality': quality,
            'prefetch': 'false'
        })

    def get_search_data(self, search_term, limit=20):
        return self._get('search', params={
            'query': str(search_term),
            'offset': 0,
            'limit': limit,
            'includeContributors': 'true'
        })

    def get_page(self, pageurl, params=None):
        local_params = {
            'deviceType': 'TV',
            'locale': 'en_US',
            'mediaFormats': 'SONY_360'
        }

        if params:
            local_params.update(params)

        return self._get('pages/' + pageurl, params=local_params)

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
    
    def get_tracks_by_isrc(self, isrc):
        return self._get('tracks', params={
            'isrc': isrc
        })

    def get_favorite_tracks(self, user_id):
        return self._get('users/' + str(user_id) + '/favorites/tracks')

    def get_track_contributors(self, track_id):
        return self._get('tracks/' + str(track_id) + '/contributors')

    def get_album_contributors(self, album_id, offset: int = 0, limit: int = 100):
        return self._get('albums/' + album_id + '/items/credits', params={
            'replace': True,
            'offset': offset,
            'limit': limit,
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

    def get_type_from_id(self, id_):
        result = None
        try:
            result = self.get_album(id_)
            return 'a'
        except TidalError:
            pass
        try:
            result = self.get_artist(id_)
            return 'r'
        except TidalError:
            pass
        try:
            result = self.get_track(id_)
            return 't'
        except TidalError:
            pass
        try:
            result = self.get_video(id_)
            return 'v'
        except TidalError:
            pass

        return result


@dataclass
class SessionStorage:
    access_token: str
    refresh_token: str
    expires: datetime
    user_id: str
    country_code: str


class TidalSession(ABC):
    """
    Tidal abstract session object with all (abstract) functions needed: auth_headers(), refresh(), session_type()
    """
    def __init__(self):
        self.access_token = None
        self.refresh_token = None
        self.expires = None
        self.user_id = None
        self.country_code = None

    def set_storage(self, storage: dict):
        self.access_token = storage.get('access_token')
        self.refresh_token = storage.get('refresh_token')
        self.expires = storage.get('expires')
        self.user_id = storage.get('user_id')
        self.country_code = storage.get('country_code')

    def get_storage(self) -> dict:
        return {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'expires': self.expires,
            'user_id': self.user_id,
            'country_code': self.country_code
        }

    def get_subscription(self) -> str:
        if self.access_token:
            r = requests.get(f'https://api.tidal.com/v1/users/{self.user_id}/subscription',
                             params={'countryCode': self.country_code},
                             headers=self.auth_headers())
            if r.status_code != 200:
                raise TidalAuthError(r.json()['userMessage'])

            return r.json()['subscription']['type']

    @abstractmethod
    def auth_headers(self) -> dict:
        pass

    def valid(self):
        """
        Checks if session is still valid and returns True/False
        """
        if not isinstance(self, TidalSession):
            if self.access_token is None or datetime.now() > self.expires:
                return False

        r = requests.get('https://api.tidal.com/v1/sessions', headers=self.auth_headers())
        return r.status_code == 200

    @abstractmethod
    def refresh(self):
        pass

    @staticmethod
    def session_type() -> str:
        pass


class TidalMobileSession(TidalSession):
    """
    Tidal session object based on the mobile Android oauth flow
    """

    def __init__(self, client_token: str):
        super().__init__()
        self.TIDAL_LOGIN_BASE = 'https://login.tidal.com/api/'
        self.TIDAL_AUTH_BASE = 'https://auth.tidal.com/v1/'

        self.client_id = client_token
        self.redirect_uri = 'https://tidal.com/android/login/auth'
        self.code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=')
        self.code_challenge = base64.urlsafe_b64encode(hashlib.sha256(self.code_verifier).digest()).rstrip(b'=')
        self.client_unique_key = secrets.token_hex(8)
        self.user_agent = 'Mozilla/5.0 (Linux; Android 13; Pixel 8 Build/TQ2A.230505.002; wv) AppleWebKit/537.36 ' \
                          '(KHTML, like Gecko) Version/4.0 Chrome/119.0.6045.163 Mobile Safari/537.36'

    def auth(self, username: str, password: str):
        s = requests.Session()

        params = {
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'lang': 'en_US',
            'appMode': 'android',
            'client_id': self.client_id,
            'client_unique_key': self.client_unique_key,
            'code_challenge': self.code_challenge,
            'code_challenge_method': 'S256',
            'restrict_signup': 'true'
        }

        # retrieve csrf token for subsequent request
        r = s.get('https://login.tidal.com/authorize', params=params, headers={
            'user-agent': self.user_agent,
            'accept-language': 'en-US',
            'x-requested-with': 'com.aspiro.tidal'
        })

        if r.status_code == 400:
            raise TidalAuthError("Authorization failed! Is the clientid/token up to date?")
        elif r.status_code == 403:
            raise TidalAuthError("TIDAL BOT protection, try again later!")

        # try Tidal DataDome cookie request
        r = s.post('https://dd.tidal.com/js/', data={
            'jsData': f'{{"opts":"endpoint,ajaxListenerPath","ua":"{self.user_agent}"}}',
            'ddk': '1F633CDD8EF22541BD6D9B1B8EF13A',  # API Key (required)
            'Referer': quote(r.url),  # Referer authorize link (required)
            'responsePage': 'origin',  # useless?
            'ddv': '4.17.0'  # useless?
        }, headers={
            'user-agent': self.user_agent,
            'content-type': 'application/x-www-form-urlencoded'
        })

        if r.status_code != 200 or not r.json().get('cookie'):
            raise TidalAuthError("TIDAL BOT protection, could not get DataDome cookie!")

        # get the cookie from the json request and save it in the session
        dd_cookie = r.json().get('cookie').split(';')[0]
        s.cookies[dd_cookie.split('=')[0]] = dd_cookie.split('=')[1]

        # enter email, verify email is valid
        r = s.post(self.TIDAL_LOGIN_BASE + 'email', params=params, json={
            'email': username
        }, headers={
            'user-agent': self.user_agent,
            'x-csrf-token': s.cookies['_csrf-token'],
            'accept': 'application/json, text/plain, */*',
            'content-type': 'application/json',
            'accept-language': 'en-US',
            'x-requested-with': 'com.aspiro.tidal'
        })

        if r.status_code != 200:
            raise TidalAuthError(r.text)

        if not r.json()['isValidEmail']:
            raise TidalAuthError('Invalid email')
        if r.json()['newUser']:
            raise TidalAuthError('User does not exist')

        # login with user credentials
        r = s.post(self.TIDAL_LOGIN_BASE + 'email/user/existing', params=params, json={
            'email': username,
            'password': password
        }, headers={
            'User-Agent': self.user_agent,
            'x-csrf-token': s.cookies['_csrf-token'],
            'accept': 'application/json, text/plain, */*',
            'content-type': 'application/json',
            'accept-language': 'en-US',
            'x-requested-with': 'com.aspiro.tidal'
        })

        if r.status_code != 200:
            raise TidalAuthError(r.text)

        # retrieve access code
        r = s.get('https://login.tidal.com/success', allow_redirects=False, headers={
            'user-agent': self.user_agent,
            'accept-language': 'en-US',
            'x-requested-with': 'com.aspiro.tidal'
        })

        if r.status_code == 401:
            raise TidalAuthError('Incorrect password')
        assert (r.status_code == 302)
        url = urlparse.urlparse(r.headers['location'])
        oauth_code = parse_qs(url.query)['code'][0]

        # exchange access code for oauth token
        r = requests.post(self.TIDAL_AUTH_BASE + 'oauth2/token', data={
            'code': oauth_code,
            'client_id': self.client_id,
            'grant_type': 'authorization_code',
            'redirect_uri': self.redirect_uri,
            'scope': 'r_usr w_usr w_sub',
            'code_verifier': self.code_verifier,
            'client_unique_key': self.client_unique_key
        }, headers={
            'User-Agent': self.user_agent
        })

        if r.status_code != 200:
            raise TidalAuthError(r.text)

        self.access_token = r.json()['access_token']
        self.refresh_token = r.json()['refresh_token']
        self.expires = datetime.now() + timedelta(seconds=r.json()['expires_in'])

        r = requests.get('https://api.tidal.com/v1/sessions', headers=self.auth_headers())

        if r.status_code != 200:
            raise TidalAuthError(r.text)

        self.user_id = r.json()['userId']
        self.country_code = r.json()['countryCode']

    def refresh(self):
        assert (self.refresh_token is not None)
        r = requests.post(self.TIDAL_AUTH_BASE + 'oauth2/token', data={
            'refresh_token': self.refresh_token,
            'client_id': self.client_id,
            'grant_type': 'refresh_token'
        })

        if r.status_code == 200:
            # print('TIDAL: Refreshing token successful')
            self.access_token = r.json()['access_token']
            self.expires = datetime.now() + timedelta(seconds=r.json()['expires_in'])

            if 'refresh_token' in r.json():
                self.refresh_token = r.json()['refresh_token']

        elif r.status_code == 401:
            print('\tERROR: ' + r.json()['userMessage'])

        return r.status_code == 200

    @staticmethod
    def session_type():
        return 'Mobile'

    def auth_headers(self):
        return {
            'Host': 'api.tidal.com',
            'X-Tidal-Token': self.client_id,
            'Authorization': 'Bearer {}'.format(self.access_token),
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip',
            'User-Agent': 'TIDAL_ANDROID/1039 okhttp/3.14.9'
        }


class TidalTvSession(TidalSession):
    """
    Tidal session object based on the AndroidTV oauth flow
    """

    def __init__(self, client_token: str, client_secret: str):
        super().__init__()
        self.TIDAL_AUTH_BASE = 'https://auth.tidal.com/v1/'

        self.client_id = client_token
        self.client_secret = client_secret

        self.access_token = None
        self.refresh_token = None
        self.expires = None
        self.user_id = None
        self.country_code = None

    def auth(self):
        s = requests.Session()

        # retrieve csrf token for subsequent request
        r = s.post(self.TIDAL_AUTH_BASE + 'oauth2/device_authorization', data={
            'client_id': self.client_id,
            'scope': 'r_usr w_usr'
        })

        if r.status_code != 200:
            raise TidalAuthError("Authorization failed! Is the clientid/token up to date?")
        else:
            device_code = r.json()['deviceCode']
            user_code = r.json()['userCode']
            print('Opening https://link.tidal.com/{}, log in or sign up to TIDAL.'.format(user_code))
            webbrowser.open('https://link.tidal.com/' + user_code, new=2)

        data = {
            'client_id': self.client_id,
            'device_code': device_code,
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
            r = requests.post(self.TIDAL_AUTH_BASE + 'oauth2/token', data=data)
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

        r = requests.get('https://api.tidal.com/v1/sessions', headers=self.auth_headers())
        assert (r.status_code == 200)
        self.user_id = r.json()['userId']
        self.country_code = r.json()['countryCode']

        r = requests.get('https://api.tidal.com/v1/users/{}?countryCode={}'.format(self.user_id, self.country_code),
                         headers=self.auth_headers())
        assert (r.status_code == 200)
        # self.username = r.json()['username']

    def refresh(self):
        assert (self.refresh_token is not None)
        r = requests.post(self.TIDAL_AUTH_BASE + 'oauth2/token', data={
            'refresh_token': self.refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'refresh_token'
        })

        if r.status_code == 200:
            # print('TIDAL: Refreshing token successful')
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
            'X-Tidal-Token': self.client_id,
            'Authorization': 'Bearer {}'.format(self.access_token),
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip',
            'User-Agent': 'TIDAL_ANDROID/1039 okhttp/3.14.9'
        }
