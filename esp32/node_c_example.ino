#include <WiFi.h>
#include <HTTPClient.h>

const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* LOG_EVENT_URL = "http://192.168.1.20/api/v1/log_event";
const char* CHECK_TICKET_URL = "http://192.168.1.20/api/v1/check_ticket?plate=";
const int BARRIER_GPIO = 12;

bool capturePlateImage(uint8_t** imageData, size_t* imageSize) {
  static const uint8_t fakeJpeg[] = {0xFF, 0xD8, 0xFF, 0xD9};
  *imageData = (uint8_t*)fakeJpeg;
  *imageSize = sizeof(fakeJpeg);
  return true;
}

String uploadGateEvent(const String& plateOverride) {
  uint8_t* imageData = nullptr;
  size_t imageSize = 0;
  if (!capturePlateImage(&imageData, &imageSize)) {
    return "";
  }

  HTTPClient http;
  WiFiClient client;
  String boundary = "----UNILAGBoundary7MA4YWxkTrZu0gW";
  String timestamp = String((unsigned long)time(nullptr));
  String body;
  body += "--" + boundary + "\r\n";
  body += "Content-Disposition: form-data; name=\"node_id\"\r\n\r\n";
  body += "C\r\n";
  body += "--" + boundary + "\r\n";
  body += "Content-Disposition: form-data; name=\"timestamp\"\r\n\r\n";
  body += timestamp + "\r\n";
  body += "--" + boundary + "\r\n";
  body += "Content-Disposition: form-data; name=\"plate_text_override\"\r\n\r\n";
  body += plateOverride + "\r\n";

  String fileHeader;
  fileHeader += "--" + boundary + "\r\n";
  fileHeader += "Content-Disposition: form-data; name=\"plate_image\"; filename=\"gate.jpg\"\r\n";
  fileHeader += "Content-Type: image/jpeg\r\n\r\n";
  String tail = "\r\n--" + boundary + "--\r\n";
  size_t totalLength = body.length() + fileHeader.length() + imageSize + tail.length();

  http.begin(client, LOG_EVENT_URL);
  http.addHeader("Content-Type", "multipart/form-data; boundary=" + boundary);
  http.addHeader("Content-Length", String(totalLength));

  int code = http.sendRequest("POST", (uint8_t*)nullptr, totalLength);
  if (code <= 0) {
    http.end();
    return "";
  }

  WiFiClient* stream = http.getStreamPtr();
  stream->print(body);
  stream->print(fileHeader);
  stream->write(imageData, imageSize);
  stream->print(tail);

  String response = http.getString();
  http.end();
  return response;
}

bool checkTicket(const String& plate) {
  HTTPClient http;
  WiFiClient client;
  http.begin(client, String(CHECK_TICKET_URL) + plate);
  int code = http.GET();
  if (code <= 0) {
    http.end();
    return false;
  }

  String response = http.getString();
  http.end();
  return response.indexOf("\"DENY\"") == -1;
}

void setBarrier(bool openBarrier) {
  digitalWrite(BARRIER_GPIO, openBarrier ? HIGH : LOW);
}

void setup() {
  Serial.begin(115200);
  pinMode(BARRIER_GPIO, OUTPUT);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
  }
  configTime(0, 0, "pool.ntp.org");
}

void loop() {
  String plateOverride = "LAG123AA";  // Remove in production.
  String logResponse = uploadGateEvent(plateOverride);
  Serial.println(logResponse);

  bool allowed = checkTicket(plateOverride);
  setBarrier(allowed);

  delay(15000);
}
