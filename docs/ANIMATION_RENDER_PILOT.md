# Animation Atlas 第二階段：精確動作渲染小樣本

此工具透過本機的 `tools/render_portraits.py` 渲染；**不包含或上傳你的原始渲染器**。此階段仍不更改網站。

## 安裝與檢查

假設 `atlas-scanner` 在 `~/Downloads/cobblemon-render-lab/cobblemon-bedrock/atlas-scanner`：

```bash
cd ~/Downloads/cobblemon-render-lab/cobblemon-bedrock/atlas-scanner
git pull --ff-only origin feat/animation-manifest-scanner-phase1
python3 -m unittest discover -s tools -p 'test_*.py'
```

先以 `--dry-run` 確認 Manifest 有指定動作（無需渲染）：

```bash
python3 tools/render_action_jobs.py \
  --repo .. \
  --manifest scan-output/animation-actions.json \
  --forms 0130_gyarados_mega 0249_lugia 0094_gengar \
  --actions air_idle air_fly water_swim blink \
  --dry-run
```

先從 Mega 暴鯉龍的 `air_idle` 一個動作做實驗，以減少重算時間與錯誤範圍：

```bash
python3 tools/render_action_jobs.py \
  --repo .. \
  --manifest scan-output/animation-actions.json \
  --forms 0130_gyarados_mega \
  --actions air_idle \
  --seconds 2 --fps 12 --size 224 --ss 2
```

如有成功輸出，結果會位於：

- `../captures/atlas_action_pilot/0130_gyarados_mega/air_idle.webp`
- `../captures/atlas_action_pilot/render-jobs.json`

Mac Finder 可用 `open ../captures/atlas_action_pilot` 開啟輸出目錄；請在有桌面的終端機執行。

## 驗證語意與限制

- 使用 Manifest 的 **完整 clip_key、source_pack、animation_path、source SHA-256**，不再自動選擇另一個「最像待機」的 clip。
- 共用 Poser 的動作可能需要 base pose + action 的合成與遊戲條件；本版每個 job 僅渲染單一 clip，因此即使骨骼匹配，畫面仍須人工審核。
- 使用原始渲染器的 `frame=cobblemon` 固定投影，避免 `fit` 每幀重算造成縮放抖動。若影格觸及邊界，最多自動調整固定相機 4 次（`--auto-frame-attempts`），保持整個動作共用同一構圖。仍無法留出 `--frame-padding` 指定的預設 6 像素時，會以 `touches_canvas_edge_review_crop` 標記失敗。
- 先檢查輸出前影格，再把 WebP 寫到 `.tmp.webp`，使用 Pillow 重讀每一幀，確認影格數與動作仍可見後才原子改名。
- 以 `render-jobs.json` 記錄耗時、骨架來源、動態像素數、輸出路徑和失敗原因。每個動作寫完立即更新報表，中斷後已完成且設定未變的工作可跳過。
- 既有動作輸出預設不覆蓋；如來源或設定改變而路徑仍存在，會要求改 `--out` 或明確 `--overwrite`。
- 目前沒有測量渲染加速倍率，也沒有保證所有 70 筆候選皆可渲染。此工具尚未在你的 Mac 實際原始資源上執行。
- 第一輪先不要將輸出回填正式網站 Manifest 的 `ready` 狀態；通過人工動作語義驗收後才考慮發布。
