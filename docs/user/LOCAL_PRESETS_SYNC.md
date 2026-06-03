# Local Presets & Encrypted Sync

This document details the design, encryption formats, and sync workflows for configuration presets in `silukman_video_enhancer`.

---

## 1. Overview & Purpose

In a local-first application, preserving user privacy is paramount. Users often create customized enhancement presets containing sensitive configuration details, including:
*   Local filesystem input and output absolute paths.
*   Hardware execution provider names and local GPU device IDs.
*   Custom restoration models, scene classifiers, and region-of-interest coordinates.
*   Network paths and credentials for render farm endpoints.

To allow users to export, back up, or sync these presets across their local network (e.g., using Syncthing, local NAS, or USB drives) without exposing sensitive metadata, the app implements **Local-first Encrypted Presets**.

---

## 2. Encryption Mechanism

Configuration presets are serialized to JSON and then encrypted using a user-provided passphrase (secret key). The encryption utilizes the baseline cryptographic functions defined in the `models/encryption.py` module:

```text
EnhancementConfig (Dataclass)
     │
     ▼ [asdict Serialization]
JSON Payload (Bytes)
     │
     ▼ [encrypt_bytes(payload, passphrase)]
Encrypted Payload (Binary file)
```

This zero-knowledge architecture ensures that preset configurations are completely unreadable to unauthorized local users, cloud sync clients, or network snoopers.

---

## 3. Core API Functions

The preset management system is exposed through three primary helpers in the `app.presets` module:

### `export_encrypted_preset(config, output_path, secret)`
Serializes the given `EnhancementConfig` instance, encrypts the output bytes using the secret passphrase, and writes the results to the specified file.

### `import_encrypted_preset(input_path, secret)`
Reads the binary preset file, decrypts the bytes using the user's secret key, and parses the JSON back into a valid, strongly typed `EnhancementConfig` object.

### `sync_encrypted_preset(source_path, sync_dir)`
Atomically copies the encrypted preset file into a target local sync directory (e.g., a network folder shared among rendering nodes).

---

## 4. Local-first Sync Workflow

Presets can be distributed to other workstations and LAN render farm coordinators using standard local-first synchronization patterns:

1.  **Export**: The user exports a preset named `4k_upscale_ultra.preset` from Workstation A with a password.
2.  **Sync**: A local folder sync agent (like Syncthing or a direct LAN folder share) propagates the encrypted binary file to Workstation B.
3.  **Import**: The user on Workstation B selects the preset, inputs the password, and imports it to initialize identical pipelines instantly.

---

## 5. Verification

The preset encryption, decryption, and sync synchronization flows are fully verified in the unit test suite:

```bash
python3 -m unittest tests.test_phase4_completion
```
Specifically, the `test_encrypted_preset_round_trips_and_syncs` test guarantees cryptographic consistency and config-model mapping validity.
