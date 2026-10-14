# Local visible-player prompt models

MobileSAM assists a human's initial include/exclude selection. It does not
identify players across a match or approve a goal, shot, save or assist.

- Source: https://github.com/ChaoningZhang/MobileSAM
- Source revision: `f706ad9c4eb7f219c00d9050e46328518ffb65d2`
- Weight: `weights/mobile_sam.pt`, 40,728,226 bytes
- Weight SHA256: `6dbb90523a35330fedd7f1d3dfc66f995213d81b29a5ca8108dbcdd4e37d6c2f`
- License: Apache-2.0; original license in `MobileSAM-LICENSE.txt`
- Export: Torch 2.5.1+cpu, ONNX 1.17.0, timm 0.9.16, opset 17,
  constant folding, 1024-pixel encoder, dynamic decoder prompt count.
- Encoder: 27,969,718 bytes; SHA256
  `85dc9194671a1173fc5632fc1ffae698f3ca0c82c7b208ed618a568377380d7e`
- Decoder: 16,496,933 bytes; SHA256
  `43c7655a81b62c0f2b0e31d2bc91d3811b48d7f736ecf93b3a4a1254318241cf`

CPU serving uses ONNX Runtime 1.31.0 with two intra-op threads and one inter-op
thread. Encoder results are bounded to two cached crops. The service never
downloads weights, installs Torch or sends a frame to an external model.
Binary parts in `segmentation-assets/manifest.json` reconstruct the exact
graphs locally, atomically, with per-part and full-graph integrity checks.

The model can merge people or miss visible limbs in crowded, blurry frames.
Prompt score alone is not player evidence: a measured person must support the
target point. Foreground prompts use measured person bounds, not a full-image
box; all supported foreground alternatives are removed. Contradictory or
unresolved points produce no mask. A human can add visible parts, mark another
foreground part or choose a clearer moment. No occluded anatomy is generated.
Behind selections always remain partial, including when a preview looks good.
