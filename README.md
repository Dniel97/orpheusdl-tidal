<!-- PROJECT INTRO -->

OrpheusDL - TIDAL
=================

A TIDAL module for the OrpheusDL modular archival music program

[Report Bug](https://github.com/Dniel97/orpheusdl-tidal/issues)
·
[Request Feature](https://github.com/Dniel97/orpheusdl-tidal/issues)


## Table of content

- [About OrpheusDL - TIDAL](#about-orpheusdl---tidal)
- [Getting Started](#getting-started)
    - [Prerequisites](#prerequisites)
    - [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
    - [Global](#global)
    - [TIDAL](#tidal)
- [Contact](#contact)
- [Acknowledgements](#acknowledgements)



<!-- ABOUT ORPHEUS -->
## About OrpheusDL - TIDAL

OrpheusDL - TIDAL is a module written in Python which allows archiving from **[tidal.com](https://listen.tidal.com)** for the modular music archival program.


<!-- GETTING STARTED -->
## Getting Started

Follow these steps to get a local copy of Orpheus up and running:

### Prerequisites

* Already have [OrpheusDL](https://github.com/yarrm80s/orpheusdl) installed

### Installation

1. Go to your `orpheusdl/` directory and run the following command:
   ```sh
   git clone --recurse-submodules https://github.com/Dniel97/orpheusdl-tidal.git modules/tidal
   ```
2. Execute:
   ```sh
   python orpheus.py
   ```
3. Now the `config/settings.json` file should be updated with the [TIDAL settings](#tidal)

<!-- USAGE EXAMPLES -->
## Usage

Just call `orpheus.py` with any link you want to archive:

```sh
python orpheus.py https://tidal.com/browse/album/92265334
```

<!-- CONFIGURATION -->
## Configuration

You can customize every module from Orpheus individually and also set general/global settings which are active in every
loaded module. You'll find the configuration file here: `config/settings.json`

### Global

```json5
"global": {
    "general": {
        // ...
        "download_quality": "lossless"
    },
    "formatting": {
        "album_format": "{artist}/{name}{quality}{explicit}"
        // ...
    },
    "codecs": {
        "proprietary_codecs": false,
        "spatial_codecs": true
    },
    "covers": {
	    "main_resolution": 1400
	    // ...
    }
    // ...
}
```

`download_quality`: Choose one of the following settings:
* "hifi": FLAC with MQA up to 48/24
* "lossless": FLAC with 44.1/16 (is MQA if the album is available in MQA)
* "high": same as "medium"
* "medium": AAC 320 kbit/s
* "low": same as "minimum"
* "minimum": AAC 96 kbit/s

`album_format`:
* `{quality}` will add
    ```
     [Dolby Atmos]
     [360]
     [M]
    ```
  depending on the album quality (with a space in at the first character)
* `{explicit}` will add
    ```
     [E]
    ```
  to the album path (with a space in at the first character)

`proprietary_codecs`: Enables/Disables MQA (Tidal Masters) downloading regardless the "hifi" setting from `download_quality`

`spatial_codecs`: Enables/Disables downloading of Dolby Atmos (EAC-3, AC-4) and Sony 360RA

`main_resolution`: Tidal only supports 80x80, 160x160, 320x320, 480x480, 640x640, 1080x1080 and 1280x1280px
(1280px won't work for playlists). If you choose 1400 or anything above 1280, it will get the highest quality even if 
the highest is 4000x4000px. That's because Tidal doesn't provide the "origin artwork" size, so the module will just get
the largest. 

### TIDAL
```json
{
    "tv_token": "7m7Ap0JC9j1cOM3n",
    "tv_secret": "vRAdA108tlvkJpTsGZS8rGZ7xTlbJ0qaZ2K9saEzsgY=",
    "mobile_atmos_token": "dN2N95wCyEBTllu4",
    "mobile_default_token": "WAU9gXp3tHhK4Nns",
    "enable_mobile": true,
    "force_non_spatial": false,
    "prefer_ac4": false,
    "fix_mqa": true
}
```

| Option            | Info                                                                                                                                                                                                                                                                                            |
|-------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| tv_token          | Enter a valid TV client token                                                                                                                                                                                                                                                                   |
| tv_secret         | Enter a valid TV client secret for the `tv_token`                                                                                                                                                                                                                                               |
| mobile_*          | Enter a valid MOBILE client token for the desired session                                                                                                                                                                                                                                       |
| enable_mobile     | Enables a second MOBILE session which needs a `username` and `password` (can be the same "TV" account) to archive Sony 360RA and Dolby AC-4 if available or allows `force_non_spatial` to work properly                                                                                         |
| force_non_spatial | Forces a default Mobile session (`mobile_default_token` without support for Dolby Atmos at all, Sony 360RA will still be available) to get FLAC/AAC tracks                                                                                                                                      |
| prefer_ac4        | If enabled and a mobile session is available (`enable_mobile` is set to `true`) this will ensure to get Dolby AC-4 on Dolby Atmos tracks                                                                                                                                                        |
| fix_mqa           | If enabled it will download the MQA file before the actual track and analyze the FLAC file to extract the bitDepth and originalSampleRate. The tags `MQAENCODER`, `ENCODER` and `ORIGINALSAMPLERATE` are than added to the FLAC file in order to get properly detected my MQA enabled software. |


**Credits: [MQA_identifier](https://github.com/purpl3F0x/MQA_identifier) by
[@purpl3F0x](https://github.com/purpl3F0x) and [mqaid](https://github.com/redsudo/mqaid) by
[@redsudo](https://github.com/redsudo).**

**NOTE: `fix_mqa` is experimental! May be slower as a download with `fix_mqa` disabled and could be incorrect**

<!-- Contact -->
## Contact

Yarrm80s (pronounced 'Yeargh mateys!') - [@yarrm80s](https://github.com/yarrm80s)

Dniel97 - [@Dniel97](https://github.com/Dniel97)

Project Link: [OrpheusDL TIDAL Public GitHub Repository](https://github.com/Dniel97/orpheusdl-tidal)


<!-- ACKNOWLEDGEMENTS -->
## Acknowledgements
* [RedSudos's RedSea fork](https://github.com/redsudo/RedSea)
* [My RedSea fork](https://github.com/Dniel97/RedSea)
