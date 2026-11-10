# Skip mask decoding for already-discarded boxes

Move the existing clipped-box area gate before mask matrix multiplication, sigmoid and full-image resize. Model forward execution, preprocessing, NMS, selection order, first-24 cap and all retained mask calculations remain unchanged. No lower-ranked box is promoted to replace a discarded one.

26 mask-decoding tests passed. New cases cover boxes beyond all four image edges, exact retained binary masks, verification that only retained masks execute sigmoid, and no refill beyond the first 24 selected indices. This removes known wasted decoder work only when a selected box has empty clipped area. No whole-analysis or measured production speedup is claimed. It does not reduce the model's expensive forward pass. No deployment or CPU allocation change.
