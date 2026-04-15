import AVFoundation
import Dispatch
import Foundation

struct CaptureResponse: Encodable {
    let ok: Bool
    let deviceLabel: String?
    let mimeType: String?
    let message: String?
    let errorCode: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case deviceLabel = "device_label"
        case mimeType = "mime_type"
        case message
        case errorCode = "error_code"
    }
}

enum HelperError: Error {
    case usage
    case authorization(String)
    case deviceUnavailable(String)
    case captureFailed(String)
    case timeout
}

final class PhotoCaptureDelegate: NSObject, AVCapturePhotoCaptureDelegate {
    private let semaphore: DispatchSemaphore
    var photoData: Data?
    var captureError: Error?

    init(semaphore: DispatchSemaphore) {
        self.semaphore = semaphore
    }

    func photoOutput(_ output: AVCapturePhotoOutput, didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
        if let error {
            captureError = error
        } else {
            photoData = photo.fileDataRepresentation()
        }
        semaphore.signal()
    }
}

func printResponse(_ response: CaptureResponse) {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    if let data = try? encoder.encode(response), let text = String(data: data, encoding: .utf8) {
        print(text)
    } else {
        print("{\"error_code\":\"json_encode_failed\",\"message\":\"Failed to encode response.\",\"ok\":false}")
    }
}

func waitForCameraAuthorization() throws {
    switch AVCaptureDevice.authorizationStatus(for: .video) {
    case .authorized:
        return
    case .notDetermined:
        let semaphore = DispatchSemaphore(value: 0)
        var granted = false
        AVCaptureDevice.requestAccess(for: .video) { ok in
            granted = ok
            semaphore.signal()
        }
        if semaphore.wait(timeout: .now() + 10) == .timedOut {
            throw HelperError.timeout
        }
        if !granted {
            throw HelperError.authorization("Camera permission was denied.")
        }
    case .denied:
        throw HelperError.authorization("Camera permission was denied.")
    case .restricted:
        throw HelperError.authorization("Camera permission is restricted on this Mac.")
    @unknown default:
        throw HelperError.authorization("Camera permission state is unknown.")
    }
}

func devicePriority(_ device: AVCaptureDevice) -> Int {
    let label = device.localizedName.lowercased()
    var score = 0
    if label.contains("macbook") && label.contains("camera") {
        score += 120
    }
    if label.contains("facetime") || label.contains("built-in") {
        score += 100
    }
    if label.contains("continuity") {
        score += 40
    }
    if label.contains("desk view") {
        score -= 40
    }
    if label.contains("screen") {
        score -= 100
    }
    if label.contains("display") {
        score -= 20
    }
    return score
}

func selectDevice(preferredLabel: String?) throws -> AVCaptureDevice {
    let devices = AVCaptureDevice.devices(for: .video)
    guard !devices.isEmpty else {
        throw HelperError.deviceUnavailable("No video capture devices are available.")
    }
    if let preferredLabel, let exact = devices.first(where: { $0.localizedName == preferredLabel }) {
        return exact
    }
    return devices.max(by: { devicePriority($0) < devicePriority($1) }) ?? devices[0]
}

func probeDevice(preferredLabel: String?) throws -> String {
    try waitForCameraAuthorization()
    let device = try selectDevice(preferredLabel: preferredLabel)
    return device.localizedName
}

func capturePhoto(to outputURL: URL, preferredLabel: String?) throws -> String {
    try waitForCameraAuthorization()
    let device = try selectDevice(preferredLabel: preferredLabel)

    let session = AVCaptureSession()
    session.sessionPreset = .photo

    let input = try AVCaptureDeviceInput(device: device)
    guard session.canAddInput(input) else {
        throw HelperError.captureFailed("Unable to attach the selected camera input.")
    }
    session.addInput(input)

    let output = AVCapturePhotoOutput()
    guard session.canAddOutput(output) else {
        throw HelperError.captureFailed("Unable to attach the camera photo output.")
    }
    session.addOutput(output)

    session.startRunning()
    Thread.sleep(forTimeInterval: 0.4)

    let semaphore = DispatchSemaphore(value: 0)
    let delegate = PhotoCaptureDelegate(semaphore: semaphore)
    let settings = AVCapturePhotoSettings(format: [AVVideoCodecKey: AVVideoCodecType.jpeg])
    output.capturePhoto(with: settings, delegate: delegate)

    if semaphore.wait(timeout: .now() + 12) == .timedOut {
        session.stopRunning()
        throw HelperError.timeout
    }
    session.stopRunning()

    if let error = delegate.captureError {
        throw HelperError.captureFailed(error.localizedDescription)
    }
    guard let data = delegate.photoData, !data.isEmpty else {
        throw HelperError.captureFailed("No image data was returned from the camera.")
    }
    try data.write(to: outputURL)
    return device.localizedName
}

func errorResponse(for error: Error) -> CaptureResponse {
    switch error {
    case HelperError.usage:
        return CaptureResponse(ok: false, deviceLabel: nil, mimeType: nil, message: "Usage: apple_camera_snapshot <output_path> [preferred_label]", errorCode: "usage")
    case HelperError.authorization(let message):
        return CaptureResponse(ok: false, deviceLabel: nil, mimeType: nil, message: message, errorCode: "camera_authorization_failed")
    case HelperError.deviceUnavailable(let message):
        return CaptureResponse(ok: false, deviceLabel: nil, mimeType: nil, message: message, errorCode: "camera_device_unavailable")
    case HelperError.captureFailed(let message):
        return CaptureResponse(ok: false, deviceLabel: nil, mimeType: nil, message: message, errorCode: "camera_capture_failed")
    case HelperError.timeout:
        return CaptureResponse(ok: false, deviceLabel: nil, mimeType: nil, message: "Timed out while waiting for a camera frame.", errorCode: "camera_capture_timeout")
    default:
        return CaptureResponse(ok: false, deviceLabel: nil, mimeType: nil, message: error.localizedDescription, errorCode: "camera_capture_failed")
    }
}

do {
    guard CommandLine.arguments.count >= 2 else {
        throw HelperError.usage
    }
    if CommandLine.arguments[1] == "--probe" {
        let preferredLabel = CommandLine.arguments.count > 2 ? CommandLine.arguments[2] : nil
        let deviceLabel = try probeDevice(preferredLabel: preferredLabel)
        printResponse(CaptureResponse(ok: true, deviceLabel: deviceLabel, mimeType: nil, message: "probe_completed", errorCode: nil))
    } else {
        let outputURL = URL(fileURLWithPath: CommandLine.arguments[1])
        let preferredLabel = CommandLine.arguments.count > 2 ? CommandLine.arguments[2] : nil
        let deviceLabel = try capturePhoto(to: outputURL, preferredLabel: preferredLabel)
        printResponse(CaptureResponse(ok: true, deviceLabel: deviceLabel, mimeType: "image/jpeg", message: "capture_completed", errorCode: nil))
    }
} catch {
    printResponse(errorResponse(for: error))
    exit(1)
}
