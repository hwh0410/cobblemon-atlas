# Cobblemon Atlas — Google Colab + Google Drive 渲染

## 已建立 Drive 目的地

`Cobblemon_Atlas`：https://drive.google.com/drive/folders/1_vstU_6wWReNe9HvmJOKB7vxflMdchs7

包含 `source_packs/`、`manifests/`、`renders/`、`reports/`、`checkpoints/`。

## Mac 一次性準備（不修改原有檔案）

請在有足夠磁碟空間的 Mac 終端機執行：

```bash
cd ~/Downloads/cobblemon-render-lab/cobblemon-bedrock
mkdir -p colab-transfer
ditto -c -k --keepParent development_resource_packs colab-transfer/development_resource_packs.zip
ditto -c -k --keepParent merged_pack colab-transfer/merged_pack.zip
cp tools/render_portraits.py colab-transfer/render_portraits.py
cp atlas-scanner/scan-output/animation-actions.json colab-transfer/animation-actions.json
ls -lh colab-transfer
```

透過 Google Drive 網頁上傳：

- `development_resource_packs.zip`、`merged_pack.zip`、`render_portraits.py` → `Cobblemon_Atlas/source_packs/`
- `animation-actions.json` → `Cobblemon_Atlas/manifests/`

**注意：** 模型與材質包可能相當大；上傳前檢查剩餘 Drive 容量。不建議將來源包及自訂渲染器加入公開 GitHub。Colab 掛載 Drive 時選擇與此資料夾相同的 Google 帳號。

## Colab 執行順序

1. 在 GitHub 開啟 `notebooks/Cobblemon_Colab_Render.ipynb`，再用 Colab 開啟 Notebook。
2. 掛載 Google Drive；在授權畫面自行確認權限。
3. 依序執行 Notebook：稀疏下載程式、解壓本機暫存、讀 Manifest、`--dry-run`、CPU 渲染、GPU 微基準、結果核對。
4. 預設先測 `0130_gyarados_mega` 與 `0249_lugia` 的少量動作。要擴大批次，修改 Notebook 最上方的 `FORMS` 和 `ACTIONS`。
5. `--sync-root` 在每個渲染 job 後同步 WebP 與 `render-jobs.json` 到 Drive。下次啟動會讀回 checkpoint 並按工作雜湊跳過已完成檔案。

## CPU/GPU 實驗範圍

- CPU 測試使用真實 Geo／材質／Poser／Animation，輸出 WebP 及品質報表。
- GPU 原型使用 PyTorch CUDA，對同一組合成三角形進行重心座標、深度與 UV 數學計算。它**沒有**完成 Minecraft 材質取樣、Z-buffer 合成、骨骼動畫或 WebP 編碼，不可把微基準的速度比寫成整體渲染加速倍率。
- Colab GPU 若未配發或 GPU 裝置不可用，報表會顯示 `cuda_unavailable`，可先使用 CPU 繼續工作。
- 為減少 Drive I/O，渲染使用 Colab 暫存磁碟；只有完成的輸出與 checkpoint 同步回 Drive。Colab 執行階段可能中斷，不應以 Notebook 留存記憶體中的影格作為唯一成果。

## 驗收

在 Drive `renders/{form_id}/{action_id}.webp` 中檢查檔案，並讀取 `checkpoints/render-jobs.json`：`ready` 只代表通過影格、動態、裁切及編碼檢查；仍需人工確認姿勢語義與特殊形態骨骼。

如果源資源包變動，重新跑 Mac 掃描器、上傳新 Manifest 和壓縮包；不要依舊版 hash 繼續渲染。
