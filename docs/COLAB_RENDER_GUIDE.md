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
4. 最新版 Notebook 目前預設執行洛奇亞修復批次：`0249_lugia` 的 `air_idle`、`air_fly`。來源檢查會要求兩個動作選中 `merged_pack` 且匹配到動態骨骼；否則直接停止，不會反覆產出靜態影格。
5. `--sync-root` 在每個渲染 job 後同步 WebP 與 `render-jobs.json` 到 Drive。下次啟動會讀回 checkpoint 並按工作雜湊跳過已完成檔案。

修復批次亦會將精確來源與動態骨骼診斷寫到 `reports/source-selection-lugia.json`。若需要擴大批次，修改 Notebook 開頭 `FORMS` 和 `ACTIONS`，並保留來源驗證；若選到其他已確認有意義的靜態姿勢，需另外建立明確的靜態輸出策略，不可直接取消 WebP 動態品質閘門。

洛奇亞的大幅翅膀動作可能超出原始固定鏡頭；目前採最多 8 次縮放／置中重試（每次縮小 20%），完整影格仍需保留至少 6 像素邊界。若重試後仍裁切，保留失敗狀態，不強行保存有缺損的 WebP。

## CPU/GPU 實驗範圍

- CPU 測試使用真實 Geo／材質／Poser／Animation，輸出 WebP 及品質報表。
- GPU 原型使用 PyTorch CUDA，對同一組合成三角形進行重心座標、深度與 UV 數學計算。它**沒有**完成 Minecraft 材質取樣、Z-buffer 合成、骨骼動畫或 WebP 編碼，不可把微基準的速度比寫成整體渲染加速倍率。
- Colab GPU 若未配發或 GPU 裝置不可用，報表會顯示 `cuda_unavailable`，可先使用 CPU 繼續工作。
- 為減少 Drive I/O，渲染使用 Colab 暫存磁碟；只有完成的輸出與 checkpoint 同步回 Drive。Colab 執行階段可能中斷，不應以 Notebook 留存記憶體中的影格作為唯一成果。

## 驗收

在 Drive `renders/{form_id}/{action_id}.webp` 中檢查檔案，並讀取 `checkpoints/render-jobs.json`：`ready` 只代表通過影格、動態、裁切及編碼檢查；仍需人工確認姿勢語義與特殊形態骨骼。

如果源資源包變動，重新跑 Mac 掃描器、上傳新 Manifest 和壓縮包；不要依舊版 hash 繼續渲染。

## 10 隻 × 3 動作批次壓力測試

[開啟批次 Colab Notebook](https://colab.research.google.com/github/hwh0410/cobblemon-atlas/blob/feat/animation-manifest-scanner-phase1/notebooks/Cobblemon_Colab_Batch_Pilot.ipynb)

此 Notebook 不改動既有洛奇亞修復版 Notebook。會先從 Manifest 挑選 10 個形態（不足時自動補足），每個挑選 3 個有動態骨骼匹配的動作，優先涵蓋待機、移動、戰鬥。這是初步篩選，仍須真正渲染與解碼確認動態。

輸出使用 Google Drive `Cobblemon_Atlas`，仍是 CPU 真正渲染 224px / 12fps / 2 秒 / SS2。GPU 原型僅測光柵化算術，不代表整體渲染加速。

- `reports/batch-pilot-10-plan.json`：形態、動作、來源及匹配骨骼
- `reports/batch-pilot-10-summary.json`：僅統計本次選定的 30 個動作品質結果及耗時
- `renders/{form_id}/{action_id}.webp`：通過驗證的輸出
- `checkpoints/render-jobs.json`：續跑狀態

每隻形態各執行一次 renderer，避免 forms × actions 意外交叉組合。已完成且工作簽章一致的結果會續用；遇到失敗將保留報告，不會將有裁切或靜態失敗的 WebP 發布到站點。Notebook 需要使用者在 Colab 登入並啟動執行階段。

## 烈空坐／超夢動作語義稽核

[Colab 語義稽核 Notebook](https://colab.research.google.com/github/hwh0410/cobblemon-atlas/blob/feat/animation-manifest-scanner-phase1/notebooks/Cobblemon_Colab_Semantic_Audit.ipynb) 會讀取既有 Drive WebP、43 MB Manifest 與 checkpoint，輸出 `reports/semantic-audit/semantic-audit.json`、烈空坐每個可用動作的 6 影格接觸圖。靜態的超夢動作會以未渲染及原始失敗理由列於報告。

此流程只寫入獨立報告目錄，不改動 `renders/`、`checkpoints/` 或網站。已通過像素檢查的烈空坐兩片不應直接發布：要先人工檢查姿勢、方向和縮放。未來批次的自動選樣已排除含 `old` 與 `test` 的 clip 名稱，但此過濾不等於全面動畫相容性驗證。
