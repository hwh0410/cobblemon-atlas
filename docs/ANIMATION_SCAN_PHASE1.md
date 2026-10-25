# Animation Atlas 第一階段：本地掃描操作

這一階段**只建立候選動畫索引**，不渲染、不改動既有 1,170 張 WebP，也不改網站 UI。
沒有經過實際渲染與解碼驗證的 clip，一律保持 `status: pending`。

## Mac 執行

```bash
cd ~/Downloads/cobblemon-render-lab/cobblemon-bedrock
git clone https://github.com/hwh0410/cobblemon-atlas.git atlas-site
cd atlas-site
python3 tools/scan_animation_manifest.py --help
```

如果 `atlas-site` 已存在，改在該資料夾執行 `git pull --ff-only`，不要重複 clone。
先確認本機提取後的資源包實際路徑，以下是**示例**；請替換為你 Mac 上實際存在的資料夾：

```bash
ls -ld ../merged_pack ../development_resource_packs
python3 tools/scan_animation_manifest.py \
  --pack merged_pack=../merged_pack \
  --pack development_resource_packs=../development_resource_packs \
  --forms 0094_gengar 0249_lugia 0130_gyarados_mega \
  --dry-run
```

去除 `--dry-run` 後，產生 `scan-output/animation-actions.json` 和 `.csv`：

```bash
python3 tools/scan_animation_manifest.py \
  --pack merged_pack=../merged_pack \
  --pack development_resource_packs=../development_resource_packs \
  --forms 0094_gengar 0249_lugia 0130_gyarados_mega \
  --resume
```

掃描全部 1,170 種形態時以 `--all --resume` 取代 `--forms ...`。
若要正式輸出 `mega-showdown/data/animation-actions.json`，必須額外使用 `--publish`；此檔只能代表候選索引，**前端尚不可把 pending 動作顯示為可播放**。

驗證掃描器本身：

```bash
python3 -m unittest discover -s tools -p 'test_*.py'
```

## 輸出定義與限制

- `form_id` 直接沿用網站 `pokemon-animated.json`，區分一般與特殊形態。
- `source_pack / animation_path / animation_sha256 / render_job_key` 記錄候選來源，避免同名 clip 混用。
- `geometry_paths / poser_paths / resolver_paths` 只列掃描找到的**確切檔名或資料夾匹配**；部分由 Resolver 間接引用、共用骨架的配置，可能需要後續專屬 parser 補強。
- `dynamic_bones` 是 keyframe / MoLang 初篩；`model_bones_matched` 僅計算**同一資源包中**可確認的骨骼交集。未知的通用動畫與骨架不會因名稱相近就強行套用。
- `evidence=candidate` 不是影片通過驗證，只有 `pending`；`reason` 記錄不確定處。
- `conflict=true` 代表同名 clip 在不同資源出現不同內容，後續必須核實來源版本。
- `--resume` 根據索引與**所有已掃描資源**的 SHA-256 指紋重用結果；任何資源變更都會重新掃描受選取的形態。寫出 JSON/CSV 採暫存檔原子替換。請勿同時對同一輸出路徑啟動兩個掃描程序。
- 實際像素變化、透明背景、影格數、姿勢疊加、播放器 loop 行為與 WebP 品質，必須到第二階段 render job 才能判定。掃描器不宣稱相容或可播放。

掃描完先回傳 `scan-output/animation-actions.json`、`.csv` 及終端機摘要，便能針對三隻樣本精修 Resolver／Poser 的實際對應格式。
