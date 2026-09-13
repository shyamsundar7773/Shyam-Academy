"""Provider-neutral voice boundaries. Production microphone/audio is intentionally absent."""

from dataclasses import dataclass
from enum import StrEnum


class VoiceStatus(StrEnum):
    READY = "READY"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class VoiceResult:
    status: VoiceStatus
    text: str = ""
    audio: bytes | None = None
    message: str = ""


class VoiceInputProvider:
    provider_name = "not_configured"

    def transcribe(self, audio: bytes) -> VoiceResult:
        raise NotImplementedError


class VoiceOutputProvider:
    provider_name = "not_configured"

    def synthesize(self, text: str) -> VoiceResult:
        raise NotImplementedError


class MockSpeechToTextProvider(VoiceInputProvider):
    provider_name = "mock"

    def __init__(self, text: str = "mock transcription"):
        self.text = text

    def transcribe(self, audio: bytes) -> VoiceResult:
        if not isinstance(audio, (bytes, bytearray)) or not audio:
            return VoiceResult(VoiceStatus.FAILED, message="Audio input is empty.")
        return VoiceResult(VoiceStatus.READY, text=self.text)


class MockTextToSpeechProvider(VoiceOutputProvider):
    provider_name = "mock"

    def synthesize(self, text: str) -> VoiceResult:
        if not isinstance(text, str) or not text.strip():
            return VoiceResult(VoiceStatus.FAILED, message="Text input is empty.")
        return VoiceResult(VoiceStatus.READY, audio=text.strip().encode("utf-8"),
                           message="Mock audio payload.")


class UnconfiguredSpeechToTextProvider(VoiceInputProvider):
    def transcribe(self, audio: bytes) -> VoiceResult:
        return VoiceResult(VoiceStatus.NOT_CONFIGURED, message="Voice input is not configured.")


class UnconfiguredTextToSpeechProvider(VoiceOutputProvider):
    def synthesize(self, text: str) -> VoiceResult:
        return VoiceResult(VoiceStatus.NOT_CONFIGURED, message="Voice output is not configured.")


def voice_lifecycle(audio: bytes, input_provider: VoiceInputProvider,
                    orchestrate, output_provider: VoiceOutputProvider | None = None):
    transcription = input_provider.transcribe(audio)
    if transcription.status != VoiceStatus.READY:
        return transcription
    response = orchestrate(transcription.text)
    if output_provider is None:
        return VoiceResult(VoiceStatus.READY, text=response)
    spoken = output_provider.synthesize(response)
    return VoiceResult(spoken.status, text=response, audio=spoken.audio, message=spoken.message)


MockVoiceInputProvider = MockSpeechToTextProvider
MockVoiceOutputProvider = MockTextToSpeechProvider
