import os

import pytest

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame = pytest.importorskip("pygame")

import sounds  # noqa: E402


@pytest.fixture(autouse=True)
def mixer():
    yield
    pygame.mixer.quit()


def test_samples_are_short_and_in_range():
    for name, samples in sounds.make_samples(22050).items():
        assert 0 < len(samples) <= 22050 // 4, name  # under a quarter of a second
        assert max(abs(s) for s in samples) <= 1.0
        assert samples[-1] == pytest.approx(0, abs=0.01)  # faded out by the end


def test_16_bit_conversion_repeats_each_sample_per_channel():
    data = sounds.to_16_bit([0.0, 1.0, -1.0, 2.0], channels=2)
    assert data.typecode == "h" and data.itemsize == 2
    assert list(data) == [0, 0, 32767, 32767, -32767, -32767, 32767, 32767]  # 2.0 is clipped


def test_sounds_load_and_play():
    player = sounds.Sounds()
    assert set(player.sounds) == {"move", "capture"}
    player.play("move")
    player.play("capture")


def test_mute():
    player = sounds.Sounds()
    player.toggle_mute()
    assert player.muted
    player.play("move")  # does nothing
    player.toggle_mute()
    assert not player.muted


def test_no_audio_device_means_no_sound_but_no_crash(monkeypatch):
    def no_device(*args, **kwargs):
        raise pygame.error("No available audio device")

    pygame.mixer.quit()
    monkeypatch.setattr(pygame.mixer, "init", no_device)
    player = sounds.Sounds()
    assert player.sounds == {}
    player.play("capture")
    player.toggle_mute()
