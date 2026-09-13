"""Safe voice-ready boundary for Interview Room."""

from dataclasses import dataclass

from ai.voice import VoiceInputProvider, VoiceOutputProvider, VoiceResult, VoiceStatus, voice_lifecycle


@dataclass(frozen=True)
class InterviewVoiceTurn:
    interview_session_id: str
    question_id: str
    transcript: str
    status: VoiceStatus
    response_audio: bytes | None = None


class InterviewVoiceBoundary:
    def __init__(self, input_provider: VoiceInputProvider, output_provider: VoiceOutputProvider):
        self.input_provider = input_provider
        self.output_provider = output_provider

    def transcribe_answer(self, audio: bytes) -> VoiceResult:
        return self.input_provider.transcribe(audio)

    def speak_feedback(self, feedback: str) -> VoiceResult:
        return self.output_provider.synthesize(feedback)

    def process(self, audio: bytes, answer_handler):
        return voice_lifecycle(audio, self.input_provider, answer_handler, self.output_provider)
