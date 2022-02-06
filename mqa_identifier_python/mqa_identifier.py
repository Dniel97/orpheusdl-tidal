import io
import struct
import wave
import sys
from pathlib import Path

# needed for correct import
sys.path.append('/'.join(__file__.replace('\\', '/').split('/')[:-1]))
import flac


def twos_complement(n, bits):
    mask = 2 ** (bits - 1)
    return -(n & mask) + (n & ~mask)


def iter_i24_as_i32(data):
    for l, h in struct.iter_unpack('<BH', data):
        yield twos_complement(h << 8 | l, 24) << 8


def iter_i16_as_i32(data):
    for x, in struct.iter_unpack('<h', data):
        yield x << 16


def peek(f, n):
    o = f.tell()
    r = f.read(n)
    f.seek(o)
    return r


def original_sample_rate_decoder(c: int) -> int:
    """
    Decodes from a 4 bit int the originalSampleRate:
    0: 44100Hz
    1: 48000Hz
    4: 176400Hz
    5: 192000Hz
    8: 88200Hz
    9: 96000Hz
    12: 352800Hz
    13: 384000Hz
    if LSB is 0 then base is 44100Hz else 48000Hz
    the first 3 MSBs need to be rotated and raised to the power of 2 (so 1, 2, 4, 8, ...)
    :param c: Is a 4 bit integer
    :return: The sample rate in Hz
    """
    base = 48000 if (c & 1) == 1 else 44100
    # jesus @purpl3F0x
    multiplier = 1 << (((c >> 3) & 1) | (((c >> 2) & 1) << 1) | (((c >> 1) & 1) << 2))

    return base * multiplier


MAGIC = 51007556744  # int.from_bytes(bytes.fromhex('0be0498c88'), 'big') jesus christ


class MqaIdentifier:
    def __init__(self, flac_file_path: str or Path):
        self.is_mqa = False
        self.is_mqa_studio = False
        self.original_sample_rate = None
        self.bit_depth = 16

        self.detect(flac_file_path)

    def get_original_sample_rate(self) -> float or int:
        """
        Get the originalSampleRate in int or float depending on the frequency
        :return: sample rate in kHz
        """
        sample_rate = self.original_sample_rate / 1000
        if sample_rate.is_integer():
            return int(sample_rate)
        return sample_rate

    def _decode_flac_samples(self, flac_file_path: str or Path) -> list:
        """
        Decodes a 16/24bit flac file to a samples list

        :param flac_file_path: Path to the flac file
        :return: Returns decoded samples in a list
        """
        with open(str(flac_file_path), 'rb') as f:
            magic = peek(f, 4)

            if magic == b'fLaC':
                with flac.BitInputStream(f) as bf:
                    f = io.BytesIO()
                    # ignore EOFError
                    try:
                        flac.decode_file(bf, f, seconds=1)
                    except EOFError:
                        pass
                    f.seek(0)

            with wave.open(f) as wf:
                channel_count, sample_width, framerate, *_ = wf.getparams()

                if channel_count != 2:
                    raise ValueError('Input must be stereo')

                if sample_width == 3:
                    iter_data = iter_i24_as_i32
                    self.bit_depth = 24
                elif sample_width == 2:
                    iter_data = iter_i16_as_i32
                else:
                    raise ValueError('Input must be 16 or 24-bit')

                return list(iter_data(wf.readframes(framerate)))

    def detect(self, flac_file_path: str or Path) -> bool:
        """
        Detects if the FLAC file is a MQA file and also detects if it's MQA Studio (blue) and the originalSampleRate

        :param flac_file_path: Path to the flac file
        :return: True if MQA got detected and False if not
        """
        # get the samples from the FLAC decoder
        samples = self._decode_flac_samples(flac_file_path)
        # samples[::2] are left channel and samples[1::2] right channel samples
        channel_samples = list(zip(samples[::2], samples[1::2]))

        # dictionary to save all the buffers for 16, 17 and 18 bit shifts
        buffer = {16: 0, 17: 0, 18: 0}
        for i, sample in enumerate(channel_samples):
            # sample[0] is the left channel sample and sample[1] the right channel sample
            # perform a XOR with both samples and bitshift it by 16, 17 and 18
            buffer = {key: value | (sample[0] ^ sample[1]) >> key & 1 for key, value in buffer.items()}

            # int.from_bytes(bytes.fromhex('0be0498c88'), 'big')
            if MAGIC in buffer.values():
                # found MQA sync word
                self.is_mqa = True

                # get the bitshift position where the MAGIC was found, ugly but works
                pos = [k for k, v in buffer.items() if v == MAGIC][0]

                # get originalSampleRate
                org = 0
                for k in range(3, 7):
                    j = ((channel_samples[i + k][0]) ^ (channel_samples[i + k][1])) >> pos & 1
                    org |= j << (6 - k)

                # decode the 4 bit int to the originalSampleRate
                self.original_sample_rate = original_sample_rate_decoder(org)

                # get MQA Studio
                provenance = 0
                for k in range(29, 34):
                    j = ((channel_samples[i + k][0]) ^ (channel_samples[i + k][1])) >> pos & 1
                    provenance |= j << (33 - k)

                # check if its MQA Studio (blue)
                self.is_mqa_studio = provenance > 8

                return True
            else:
                buffer = {key: (value << 1) & 0xFFFFFFFFF for key, value in buffer.items()}

        return False
