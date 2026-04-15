import Dispatch
import Foundation
import Speech

struct TranscriptResponse: Encodable {
    let ok: Bool
    let transcriptText: String?
    let transcriptionBackend: String
    let confidence: Double?
    let message: String?
    let errorCode: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case transcriptText = "transcript_text"
        case transcriptionBackend = "transcription_backend"
        case confidence
        case message
        case errorCode = "error_code"
    }
}

enum HelperError: Error {
    case usage
    case authorization(String)
    case recognizerUnavailable(String)
    case transcriptionFailed(String)
    case timeout
}

func printResponse(_ response: TranscriptResponse) {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    if let data = try? encoder.encode(response), let text = String(data: data, encoding: .utf8) {
        print(text)
    } else {
        print("{\"error_code\":\"json_encode_failed\",\"message\":\"Failed to encode response.\",\"ok\":false,\"transcription_backend\":\"apple_speech\"}")
    }
}

func waitForSpeechAuthorization() throws {
    let semaphore = DispatchSemaphore(value: 0)
    var status: SFSpeechRecognizerAuthorizationStatus = .notDetermined
    SFSpeechRecognizer.requestAuthorization { newStatus in
        status = newStatus
        semaphore.signal()
    }

    if semaphore.wait(timeout: .now() + 10) == .timedOut {
        throw HelperError.timeout
    }

    switch status {
    case .authorized:
        return
    case .denied:
        throw HelperError.authorization("Speech recognition permission was denied.")
    case .restricted:
        throw HelperError.authorization("Speech recognition is restricted on this Mac.")
    case .notDetermined:
        throw HelperError.authorization("Speech recognition permission is not determined.")
    @unknown default:
        throw HelperError.authorization("Speech recognition permission state is unknown.")
    }
}

func averageConfidence(_ transcription: SFTranscription) -> Double? {
    guard !transcription.segments.isEmpty else {
        return nil
    }
    let total = transcription.segments.reduce(Float(0.0)) { partial, segment in
        partial + segment.confidence
    }
    return Double(total / Float(transcription.segments.count))
}

func transcribeAudio(at audioURL: URL, localeIdentifier: String) throws -> TranscriptResponse {
    try waitForSpeechAuthorization()

    guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: localeIdentifier)) else {
        throw HelperError.recognizerUnavailable("Unable to create an Apple Speech recognizer for the requested locale.")
    }
    if !recognizer.isAvailable {
        throw HelperError.recognizerUnavailable("Apple Speech recognizer is currently unavailable.")
    }

    let request = SFSpeechURLRecognitionRequest(url: audioURL)
    request.shouldReportPartialResults = false

    let semaphore = DispatchSemaphore(value: 0)
    var finalTranscription: SFTranscription?
    var finalError: Error?

    let task = recognizer.recognitionTask(with: request) { result, error in
        if let result = result {
            finalTranscription = result.bestTranscription
            if result.isFinal {
                semaphore.signal()
            }
        }

        if let error = error {
            finalError = error
            semaphore.signal()
        }
    }

    if semaphore.wait(timeout: .now() + 20) == .timedOut {
        task.cancel()
        throw HelperError.timeout
    }
    task.cancel()

    if let finalError = finalError {
        throw HelperError.transcriptionFailed(finalError.localizedDescription)
    }

    guard let transcription = finalTranscription else {
        throw HelperError.transcriptionFailed("No transcription result was returned.")
    }

    let transcriptText = transcription.formattedString.trimmingCharacters(in: .whitespacesAndNewlines)
    if transcriptText.isEmpty {
        throw HelperError.transcriptionFailed("No speech was detected in the captured audio.")
    }

    return TranscriptResponse(
        ok: true,
        transcriptText: transcriptText,
        transcriptionBackend: "apple_speech",
        confidence: averageConfidence(transcription),
        message: "transcription_completed",
        errorCode: nil
    )
}

func errorResponse(for error: Error) -> TranscriptResponse {
    switch error {
    case HelperError.usage:
        return TranscriptResponse(
            ok: false,
            transcriptText: nil,
            transcriptionBackend: "apple_speech",
            confidence: nil,
            message: "Usage: apple_speech_transcribe <audio_path> [locale]",
            errorCode: "usage"
        )
    case HelperError.authorization(let message):
        return TranscriptResponse(
            ok: false,
            transcriptText: nil,
            transcriptionBackend: "apple_speech",
            confidence: nil,
            message: message,
            errorCode: "speech_authorization_failed"
        )
    case HelperError.recognizerUnavailable(let message):
        return TranscriptResponse(
            ok: false,
            transcriptText: nil,
            transcriptionBackend: "apple_speech",
            confidence: nil,
            message: message,
            errorCode: "speech_recognizer_unavailable"
        )
    case HelperError.transcriptionFailed(let message):
        return TranscriptResponse(
            ok: false,
            transcriptText: nil,
            transcriptionBackend: "apple_speech",
            confidence: nil,
            message: message,
            errorCode: "speech_transcription_failed"
        )
    case HelperError.timeout:
        return TranscriptResponse(
            ok: false,
            transcriptText: nil,
            transcriptionBackend: "apple_speech",
            confidence: nil,
            message: "Timed out while waiting for Apple Speech transcription.",
            errorCode: "speech_transcription_timeout"
        )
    default:
        return TranscriptResponse(
            ok: false,
            transcriptText: nil,
            transcriptionBackend: "apple_speech",
            confidence: nil,
            message: error.localizedDescription,
            errorCode: "speech_transcription_failed"
        )
    }
}

do {
    guard CommandLine.arguments.count >= 2 else {
        throw HelperError.usage
    }

    let audioURL = URL(fileURLWithPath: CommandLine.arguments[1])
    let localeIdentifier = CommandLine.arguments.count > 2 ? CommandLine.arguments[2] : "en-US"
    let response = try transcribeAudio(at: audioURL, localeIdentifier: localeIdentifier)
    printResponse(response)
} catch {
    printResponse(errorResponse(for: error))
    exit(1)
}
