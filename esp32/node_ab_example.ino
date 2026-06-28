#include <WiFi.h>
#include <HTTPClient.h>

const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* SERVER_URL = "http://192.168.1.20/api/v1/log_event";
const char* NODE_ID = "A";  // Change to "B" for the exit node.

// Replace this with your actual camera JPEG capture function.
bool capturePlateImage(uint8_t** imageData, size_t* imageSize) {
  static const uint8_t fakeJpeg[] = {0xFF, 0xD8, 0xFF, 0xD9};
  *imageData = (uint8_t*)fakeJpeg;
  *imageSize = sizeof(fakeJpeg);
  return true;
}

String buildMultipartBody(const String& boundary, const String& timestamp, float dopplerFrequency, const String& plateOverride) {
  String body;
  body += "--" + boundary + "\r\n";
  body += "Content-Disposition: form-data; name=\"node_id\"\r\n\r\n";
  body += String(NODE_ID) + "\r\n";

  body += "--" + boundary + "\r\n";
  body += "Content-Disposition: form-data; name=\"timestamp\"\r\n\r\n";
  body += timestamp + "\r\n";

  body += "--" + boundary + "\r\n";
  body += "Content-Disposition: form-data; name=\"doppler_frequency\"\r\n\r\n";
  body += String(dopplerFrequency, 2) + "\r\n";

  if (plateOverride.length() > 0) {
    body += "--" + boundary + "\r\n";
    body += "Content-Disposition: form-data; name=\"plate_text_override\"\r\n\r\n";
    body += plateOverride + "\r\n";
  }

  return body;
}

void postEvent(float dopplerFrequency, const String& plateOverride) {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  uint8_t* imageData = nullptr;
  size_t imageSize = 0;
  if (!capturePlateImage(&imageData, &imageSize)) {
    return;
  }

  HTTPClient http;
  WiFiClient client;
  String boundary = "----UNILAGBoundary7MA4YWxkTrZu0gW";
  String timestamp = String((unsigned long)time(nullptr));
  String head = buildMultipartBody(boundary, timestamp, dopplerFrequency, plateOverride);
  String fileHeader;
  fileHeader += "--" + boundary + "\r\n";
  fileHeader += "Content-Disposition: form-data; name=\"plate_image\"; filename=\"capture.jpg\"\r\n";
  fileHeader += "Content-Type: image/jpeg\r\n\r\n";
  String tail = "\r\n--" + boundary + "--\r\n";

  size_t totalLength = head.length() + fileHeader.length() + imageSize + tail.length();

  http.begin(client, SERVER_URL);
  http.addHeader("Content-Type", "multipart/form-data; boundary=" + boundary);
  http.addHeader("Content-Length", String(totalLength));

  int code = http.sendRequest("POST", (uint8_t*)nullptr, totalLength);
  if (code <= 0) {
    http.end();
    return;
  }

  WiFiClient* stream = http.getStreamPtr();
  stream->print(head);
  stream->print(fileHeader);
  stream->write(imageData, imageSize);
  stream->print(tail);

  String response = http.getString();
  Serial.println(response);
  http.end();
}

void setup() {
  Serial.begin(115200);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
  }
  configTime(0, 0, "pool.ntp.org");
}

void loop() {
  // Replace this demo trigger with your radar + ultrasonic logic.
  float dopplerFrequency = 123.45f;
  String plateOverride = "LAG123AA";  // Remove in production.
  postEvent(dopplerFrequency, plateOverride);
  delay(15000);
}
