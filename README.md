<!-- PROJECT INTRO -->

OrpheusDL - Tidal
=================

A Tidal module for the OrpheusDL modular archival music program

[Report Bug](https://github.com/yarrm80s/orpheusdl/issues)
·
[Request Feature](https://github.com/yarrm80s/orpheusdl/issues)


## Table of content

- [About OrpheusDL - Tidal](#about-orpheusdl-tidal)
- [Getting Started](#getting-started)
    - [Prerequisites](#prerequisites)
    - [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
    - [Global](#global)
    - [Tidal](#tidal)
- [Contact](#contact)
- [Acknowledgements](#acknowledgements)



<!-- ABOUT ORPHEUS -->
## About OrpheusDL - Tidal

OrpheusDL - Tidal is a module written in Python which allows archiving from **Tidal** for the modular music archival program.


<!-- GETTING STARTED -->
## Getting Started

Follow these steps to get a local copy of Orpheus up and running:

### Prerequisites

* Already have [OrpheusDL](https://github.com/yarrm80s/orpheusdl) installed

### Installation

1. Clone the repo inside the folder `OrpheusDL`
   ```sh
   git clone https://github.com/Dniel97/orpheusdl-tidal.git
   ```
2. Execute:
   ```sh
   python orpheus.py search tidal track darkside
   ```
3. Now the `config/settings.json` file should be updated with the Tidal settings

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

```json
"global": {
    "general": {
        "album_search_return_only_albums": false,
        "download_path": "./downloads/",
        "download_quality": "lossless"
    },
    "codecs": {
        "proprietary_codecs": false,
        "spatial_codecs": true
    },
```

`download_quality`: Choose one of the following settings:
* "hifi": FLAC with MQA up to 48/24
* "lossless": FLAC with 44.1/16
* "high": AAC 320 kbit/s
* "low": AAC 96 kbit/s

`proprietary_codecs`: Enables/Disables MQA (Tidal Masters) downloading regardless the "hifi" setting from `download_quality`

`spatial_codecs`: Enables/Disables downloading of Dolby Atmos (EAC-3, AC-4) and Sony 360RA

### Tidal
```json
 "tidal": {
    "client_token": "",
    "client_secret": "",
}
```
`client_token`: Enter a valid TV client token

`client_secret`: Enter a valid TV client secret for the `client_token`

<!-- Contact -->
## Contact

Yarrm80s (pronounced 'Yeargh mateys!') - [@yarrm80s](https://github.com/yarrm80s)

Dniel97 - [@Dniel97](https://github.com/Dniel97)

Project Link: [OrpheusDL Tidal Public GitHub Repository](https://github.com/Dniel97/orpheusdl-tidal)


<!-- ACKNOWLEDGEMENTS -->
## Acknowledgements
* [RedSea](https://github.com/redsudo/RedSea)
* [My RedSea fork](https://github.com/Dniel97/RedSea)
