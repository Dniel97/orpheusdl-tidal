# MQA-identifier-python

An MQA (Studio, originalSampleRate) identifier for "lossless" flac files written in Python.

## About The Project

This project is a port of the awesome C++ project [MQA_identifier](https://github.com/purpl3F0x/MQA_identifier) by
[@purpl3F0x](https://github.com/purpl3F0x) and [mqaid](https://github.com/redsudo/mqaid) by
[@redsudo](https://github.com/redsudo).

## Getting Started

### Prerequisites

- [Python 3.6+](https://python.org/)

### Installation

1. Clone the repo

    ```sh
    git clone https://github.com/Dniel97/MQA-identifier-python.git && cd MQA-identifier-python
    ```

2. Install the requirements

    ```sh
    pip3 install -r requirements.txt
    ```

## Usage

```shell
python3 mqa-identifier-python.py "path/to/flac/files"
```

```
Found 11 FLAC files to check
#	Encoding				Name
1	NOT MQA					22. letzter song.flac
2	NOT MQA					23. judy.flac
3	MQA Studio 96kHz		        01. Algorithm.mqa.flac
4	MQA Studio 48kHz		        02. The Dark Side.mqa.flac
5	MQA Studio 96kHz		        03. Pressure.mqa.flac
6	MQA Studio 48kHz		        04. Propaganda.mqa.flac
7	MQA Studio 96kHz		        05. Break It to Me.mqa.flac
8	MQA Studio 96kHz		        06. Something Human.mqa.flac
9	MQA Studio 96kHz		        07. Thought Contagion.mqa.flac
10	MQA Studio 96kHz		        08. Get up and Fight.mqa.flac
11	MQA Studio 44.1kHz		        09. Blockades.mqa.flac
```

## Contributing

Pull requests are welcome.

## Related Projects

- [MQA_identifier](https://github.com/purpl3F0x/MQA_identifier) (Core)
- [mqaid](https://github.com/redsudo/mqaid)
