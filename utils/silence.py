import discord

class Silence(discord.AudioSource):
    def __init__(self):
        self.channels = 2
        self.sample_width = 2
        self.sample_rate = 48000
        # 20ms of silence
        self.frame_length = 20
        self.num_reads = 0

    def read(self):
        # Return 20ms of silence
        # Size = 2 channels * 2 bytes/sample * 48000 samples/sec * 0.02 sec = 3840 bytes
        self.num_reads += 1
        return b'\x00' * 3840

    def is_opus(self):
        # We are returning raw PCM, not Opus encoded data
        return False
