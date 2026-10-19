# イノシシ・シカ画像のJPEG圧縮評価

ESP32-S3-CAM と LPWA による罠併設カメラを想定し、イノシシ（`boar`）とシカ（`deer`）の画像を縮小・JPEG圧縮したときの画質とデータ量を評価するための作業フォルダです。

元画像は変更せず、派生画像と集計結果を `data/processed/` と `results/` に保存します。

## 必要な環境

- Python 3.11 以降
- Pillow

Pillow が未導入の場合は、次を実行します。

```bash
python3 -m pip install Pillow
```

## フォルダ構成

```text
work/
├── data/
│   ├── raw/                     # 入力画像（boar、deer）
│   │   ├── boar/
│   │   └── deer/
│   └── processed/               # 条件別に生成するJPEG画像
│       ├── vga_q95/
│       ├── qvga_q75/
│       ├── qvga_q50/
│       ├── qqvga_q75/
│       └── qqvga_q50/
├── results/                     # CSVの集計・変換記録
├── scripts/                     # 実行用Pythonスクリプト
└── README.md
```

## 実行方法

以下は、この `work` フォルダで実行します。

```bash
cd ~/2026/yamaji/test_editing/work
```

### 1. 元画像を調査する

```bash
python3 scripts/summarize_dataset.py
```

`data/raw/boar/` と `data/raw/deer/` の画像を読み込み、読み込み可否、画像形式、幅・高さ、カラーモード、ファイルサイズを記録します。

### 2. 圧縮画像を作成する

```bash
python3 scripts/generate_compressed_images.py
```

各元画像から、次の5条件のJPEG画像を作成します。

| 保存フォルダ | 解像度 | JPEG品質（Pillow） |
| --- | ---: | ---: |
| `vga_q95` | 640×480 | 95 |
| `qvga_q75` | 320×240 | 75 |
| `qvga_q50` | 320×240 | 50 |
| `qqvga_q75` | 160×120 | 75 |
| `qqvga_q50` | 160×120 | 50 |

画像の縦横比は保ち、4:3の出力サイズに収まらない部分は黒い余白で補います。そのため、画像中の動物を中央で切り抜くことはありません。JPEGは4:2:0サブサンプリングで保存します。

背景色を変えたい場合は、RGB値を指定します。例えば灰色の場合は次のとおりです。

```bash
python3 scripts/generate_compressed_images.py --background 128,128,128
```

> 同一条件で再実行すると、既存の圧縮画像と `compression_manifest.csv` は上書きされます。

## 各ファイルの説明

### `scripts/summarize_dataset.py`

元画像の基本情報を集計するスクリプトです。

| 出力ファイル | 内容 |
| --- | --- |
| `results/dataset_summary.csv` | 画像1枚ごとのクラス名、ファイル名、形式、幅・高さ、カラーモード、ファイルサイズ、読み込み可否 |
| `results/dataset_class_summary.csv` | クラスごとの枚数、破損画像数、ファイルサイズの平均・中央値・最小・最大、幅・高さの中央値 |

### `scripts/generate_compressed_images.py`

5種類の解像度・JPEG品質で派生画像を作るスクリプトです。出力先は `data/processed/<条件名>/<クラス名>/` です。

| 出力ファイル | 内容 |
| --- | --- |
| `results/compression_manifest.csv` | 元画像と圧縮画像の対応、変換条件、元・変換後のサイズ、圧縮率、縮小率、余白のピクセル数、変換成否 |

## ESP32-S3-CAMとの対応

PC上のJPEG品質（95、75、50）は、画質とファイルサイズの傾向を比較するための評価条件です。ESP32-Cameraの `jpeg_quality` は0〜63で、小さい値ほど高画質となるため、PCの品質値と1対1には対応しません。

実機では、次のようにカメラから直接JPEGを取得し、フレームバッファのバイト列をLPWAで分割送信する想定です。

```cpp
.pixel_format = PIXFORMAT_JPEG,
.frame_size = FRAMESIZE_QVGA,  // 320×240
.jpeg_quality = 12,            // ESP32では小さいほど高画質

camera_fb_t *fb = esp_camera_fb_get();
// fb->buf と fb->len を分割して送信する
esp_camera_fb_return(fb);
```

まずはPCで `qvga_q75`（320×240・品質75）を基準に評価し、実機では `FRAMESIZE_QVGA` と `jpeg_quality=12` 前後から、ファイルサイズと見え方を測定して調整します。
