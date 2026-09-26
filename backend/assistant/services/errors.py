"""Errors the API turns into clean JSON responses: {"error": {"code", "message"}}."""


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 500):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class NoInputError(ServiceError):
    """Nothing was said / the recording was empty."""

    def __init__(self, message: str = "I didn't hear anything. Please try again."):
        super().__init__("no_input", message, 422)


class UnclearAudioError(ServiceError):
    """Audio was received but no intelligible speech could be found in it."""

    def __init__(
        self,
        message: str = "I couldn't make out what you said. Please speak a little "
        "closer to the microphone and try again.",
    ):
        super().__init__("unclear_audio", message, 422)


class AudioDeviceError(ServiceError):
    """The microphone or speaker could not be used (terminal mode)."""

    def __init__(self, message: str):
        super().__init__("audio_device_error", message, 500)
