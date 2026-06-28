# ESP32 Node Integration

This folder contains Arduino-style ESP32 examples for posting node events to the Flask backend.

## API contract used by the sketches

The backend accepts:

- `POST /api/v1/log_event`
  - `multipart/form-data`
  - text fields:
    - `node_id`
    - `timestamp`
    - optional `doppler_frequency`
    - optional `plate_text_override` for bench testing
  - file field:
    - `plate_image`

## Node mapping

- `NODE_A`: entry node for section-control start
- `NODE_B`: exit node for section-control finish
- `NODE_C`: gate checker node

## Notes

- These examples assume an `ESP32-CAM`-style board with a JPEG frame buffer available.
- The sketches use multipart upload because that matches the stronger version of the backend protocol and avoids large base64 expansion on the microcontroller.
- `plate_text_override` is included as an optional debug feature. Remove it for real OCR-based operation.

## Files

- `node_ab_example.ino`: example for Nodes A and B
- `node_c_example.ino`: example for gate checker Node C
