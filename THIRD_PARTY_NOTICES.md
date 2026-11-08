# Third-party notices

This repository does not include third-party packages or data. The analysis installs BARO (`fse-baro`) and,
for the causal rankers only, RCAEval with pip; see `requirements.txt` and `requirements-causal.txt`.

One file contains a short excerpt adapted from RCAEval:

* `analysis/camera_ready/rankers/step2_causal.py`, function `circa_rank`: the conversion of the PC adjacency
  matrix into a call graph, the construction of the data loader, and the `CaseData` set-up follow RCAEval's
  `circa()` / `rht()` code (about 35 lines, marked in the file). The rest of the file is the authors' own code.

RCAEval licence:

```
MIT License

Copyright (c) 2024 Luan Pham

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
