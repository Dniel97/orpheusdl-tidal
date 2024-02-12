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
    - [Updating](#updating)
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

1. Go to your already cloned `orpheusdl/` directory and run the following command:
   ```sh
   git clone --recurse-submodules https://github.com/Dniel97/orpheusdl-tidal.git modules/tidal
   ```
2. Execute:
   ```sh
   python orpheus.py
   ```
3. Now the `config/settings.json` file should be updated with the [TIDAL settings](#tidal)

### Updating

1. Go to your already cloned `orpheusdl/` directory and run the following command:
   ```sh
   git -C modules/tidal pull
   ```
2. Execute to update your already existing TIDAL settings (if needed):
   ```sh
   python orpheus.py
   ```
3. Now the `config/settings.json` file should be updated with the new updated [TIDAL settings](#tidal)


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
        "download_quality": "hifi"
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

#### `download_quality`

Choose one of the following settings:

| Quality    | Info                                                                                 |
|------------|--------------------------------------------------------------------------------------|
| `hifi`     | FLAC up to 192/24 **or** MQA (FLAC) up to 48/24 when `proprietary_codecs` is enabled |
| `lossless` | FLAC with 44.1/16 (is MQA if the album is available in MQA)                          |
| `high`     | same as `medium`                                                                     |
| `medium`   | AAC 320 kbit/s                                                                       |
| `low`      | same as `minimum`                                                                    |
| `minimum`  | AAC 96 kbit/s                                                                        |

**Note: HiRes will ALWAYS be preferred instead of MQA!**

#### `album_format`
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
  to the album path (with a space at the first character)


| Option             | Info                                                                                                                                                                                                                                                                                                                                                     |
|--------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| proprietary_codecs | Enables/Disables MQA (Tidal Masters) downloading when no HiRes track is available                                                                                                                                                                                                                                                                        |
| spatial_codecs     | Enables/Disables downloading of Dolby Atmos (EAC-3, AC-4) and Sony 360RA (MHA1)                                                                                                                                                                                                                                                                          |
| main_resolution    | Tidal only supports 80x80, 160x160, 320x320, 480x480, 640x640, 1080x1080 and 1280x1280px (1280px won't work for playlists). <br/>If you choose 1400 or anything above 1280, it will get the highest quality even if the highest is 4000x4000px. That's because Tidal doesn't provide the "origin artwork" size, so the module will just get the largest. |

### TIDAL
```json
{
    "tv_atmos_token": "4N3n6Q1x95LL5K7p",
    "tv_atmos_secret": "oKOXfJW371cX6xaZ0PyhgGNBdNLlBZd4AKKYougMjik=",
    "mobile_atmos_hires_token": "km8T1xS355y7dd3H",
    "mobile_hires_token": "6BDSRdpK9hqEBTgU",
    "enable_mobile": true,
    "prefer_ac4": false,
    "fix_mqa": true
}
```

| Option        | Info                                                                                                                                                                                                                                                                                                                            |
|---------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| tv_token      | Enter a valid TV client token                                                                                                                                                                                                                                                                                                   |
| tv_secret     | Enter a valid TV client secret for the `tv_token`                                                                                                                                                                                                                                                                               |
| mobile_*      | Enter a valid MOBILE client token for the desired session                                                                                                                                                                                                                                                                       |
| enable_mobile | Enables a MOBILE session to archive Sony 360RA and Dolby AC-4 if available                                                                                                                                                                                                                                                      |
| prefer_ac4    | If enabled and a mobile session is available (`enable_mobile` is set to `true`) this will ensure to get Dolby AC-4 on Dolby Atmos tracks                                                                                                                                                                                        |
| fix_mqa       | If enabled it will download the MQA file before the actual track and analyze the FLAC file to extract the bitDepth and originalSampleRate. The tags `MQAENCODER`, `ENCODER` and `ORIGINALSAMPLERATE` are than added to the FLAC file in order to get properly detected by MQA enabled software such as Roon, UAPP or Audirvana. |


**Credits: [MQA_identifier](https://github.com/purpl3F0x/MQA_identifier) by
[@purpl3F0x](https://github.com/purpl3F0x) and [mqaid](https://github.com/redsudo/mqaid) by
[@redsudo](https://github.com/redsudo).**

**NOTE: `fix_mqa` may be slower as a download without `fix_mqa` and could be incorrect.**

<!-- Contact -->
## Contact

Yarrm80s (pronounced 'Yeargh mateys!') - [@yarrm80s](https://github.com/yarrm80s)

Dniel97 - [@Dniel97](https://github.com/Dniel97)

Project Link: [OrpheusDL TIDAL Public GitHub Repository](https://github.com/Dniel97/orpheusdl-tidal)


<!-- ACKNOWLEDGEMENTS -->
## Acknowledgements
* [RedSudos's RedSea fork](https://github.com/redsudo/RedSea)
* [My RedSea fork](https://github.com/Dniel97/RedSea)
