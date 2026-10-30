"""Move and capture sounds, made in code so the game needs no sound files.

If the computer has no audio device the game still runs, just silently.
"""

import array
import math
import random

import pygame


def knock(sample_rate, ms, pitch, decay_ms, noise, volume, seed=0):
    """A short percussive sound, like a piece set down on a board.

    A tone whose pitch falls a little, mixed with some noise for the "click",
    fading out quickly. Returns the samples as floats between -1 and 1.
    """
    rng = random.Random(seed)
    count = sample_rate * ms // 1000
    samples = []
    phase = 0.0
    for i in range(count):
        t = i / sample_rate
        envelope = min(1.0, t / 0.002) * math.exp(-t * 1000 / decay_ms)  # 2 ms attack, then fade
        phase += 2 * math.pi * pitch * (1 - 0.35 * i / count) / sample_rate
        samples.append(volume * envelope * ((1 - noise) * math.sin(phase) + noise * rng.uniform(-1, 1)))
    return samples


def mix(*sounds):
    """Add sounds together (the result is as long as the longest one)"""
    length = max(len(sound) for sound in sounds)
    return [sum(sound[i] for sound in sounds if i < len(sound)) for i in range(length)]


def to_16_bit(samples, channels):
    """Signed 16-bit samples, repeated for each channel, ready for pygame.mixer.Sound(buffer=...)"""
    data = array.array("h")
    for sample in samples:
        value = int(max(-1.0, min(1.0, sample)) * 32767)
        data.extend([value] * channels)
    return data


def make_samples(sample_rate):
    """The game's sounds as float samples: {"move": [...], "capture": [...]}"""
    return {
        "move": knock(sample_rate, ms=90, pitch=520, decay_ms=22, noise=0.25, volume=0.6),
        # Lower, longer and with a sharp crack on top
        "capture": mix(knock(sample_rate, ms=160, pitch=300, decay_ms=45, noise=0.45, volume=0.55, seed=1),
                       knock(sample_rate, ms=60, pitch=1100, decay_ms=10, noise=0.3, volume=0.35, seed=2)),
    }


class Sounds:
    def __init__(self):
        self.muted = False
        self.sounds = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except pygame.error:
            return  # no audio device: carry on without sound
        sample_rate, size, channels = pygame.mixer.get_init()
        if size != -16:  # the samples are built as signed 16-bit numbers
            return
        try:
            for name, samples in make_samples(sample_rate).items():
                self.sounds[name] = pygame.mixer.Sound(buffer=to_16_bit(samples, channels).tobytes())
        except pygame.error:
            self.sounds = {}

    def play(self, name):
        if not self.muted and name in self.sounds:
            self.sounds[name].play()

    def toggle_mute(self):
        self.muted = not self.muted
