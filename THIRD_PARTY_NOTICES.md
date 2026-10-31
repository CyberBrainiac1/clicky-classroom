# Open-source components in Clicky Classroom

Clicky retains the upstream MIT license and copyright notice in LICENSE.

Dashboard outline icons come from Lucide (https://github.com/lucide-icons/lucide). The bundled SVGs retain Lucide/Feather ISC/MIT attribution in `THIRD_PARTY_LICENSES/Lucide-ISC.txt`. They load locally without any network requests. The notes layout follows the user-supplied screenshot; it does not copy private notes or recordings into the app.

Classroom adapts OpenWhispr's MIT-licensed audio policies:

- `classroom/openwhispr_audio.py`: Python adaptations of100ms pause search,4second search window,0.5second tail allowance, and the local PCM16 speech gate from `src/helpers/parakeetSegmentation.js` and `src/helpers/localSpeechGate.js`.
- `classroom/engines.py`: required transducer filenames and NeMo decoder selection follow `src/helpers/parakeetModelInfo.js` and `src/models/modelRegistryData.json`.

Source: https://github.com/OpenWhispr/openwhispr/tree/b9e9ebefac4b961456c269164a93ddfdd53438b9

Copyright(c)2024 OpenWhispr Team. The full permission notice is included in `THIRD_PARTY_LICENSES/OpenWhispr-MIT.txt`.

This is an independent Python integration, not a connection to OpenWhispr's running app or recording server. It does not bundle OpenWhispr trademarks, credentials, private recordings, or model weights. Models and dependencies retain their own licenses. Choose compatible model files separately; a source-code license does not grant a new license for every model in an upstream catalog.
