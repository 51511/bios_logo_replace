# BIOS Logo 一鍵替換工具

> ⚠️ **免責聲明：刷壞 BIOS 我不管。使用前請確保你知道自己在做什麼。**

---

## 這是什麼

一個 Python 腳本，讓你在 Linux 上把開機時主機板顯示的 Logo 換成自己的圖片。

整個流程：備份 BIOS → 解包 → 找到 Logo → 轉換新圖 → Binary Patch → 刷回去。

---

## 前置需求

```bash
sudo apt install flashrom imagemagick cmake g++ git
```

---

## 使用方式

**測試模式（不刷入，只產生修改後的 BIOS 檔案）：**
```bash
sudo python3 bios_logo_replace.py --logo your_logo.png --skip-flash
```

**正式模式（會真的刷入）：**
```bash
sudo python3 bios_logo_replace.py --logo your_logo.png
```

**手動指定尺寸（如果自動偵測失敗）：**
```bash
sudo python3 bios_logo_replace.py --logo your_logo.png --width 409 --height 307
```

---

## 執行流程

| 步驟 | 說明 |
|------|------|
| 1 | 從 GitHub clone UEFITool 原始碼並編譯 UEFIExtract（只需第一次） |
| 2 | 用 flashrom 備份現有 BIOS → `original_bios.bin` |
| 3 | 解包 BIOS，搜尋 Logo GUID `7BB28B99-...` |
| 4 | 自動偵測原始 Logo 格式（JPEG/BMP/PNG）與尺寸 |
| 5 | 轉換新 Logo，用二分搜尋找到最接近原始大小的 JPEG 品質值 |
| 6 | Binary patch：在 BIOS bytes 中定位原始 Logo 並替換 |
| 7 | （可選）flashrom 刷入 |
| 清理 | 刪除暫存檔，保留 BIOS 備份和你的原始 Logo |

---

## 已知限制與風險

**這個腳本好不好？老實說：不確定。**

- **Binary patch 方式有風險**：直接替換 bytes 不會重新計算 UEFI volume checksum。大多數主機板會忽略 checksum 錯誤，但不是全部。
- **大小必須一致**：新 Logo 的 bytes 大小必須跟原始完全一樣，腳本會嘗試用 JPEG 品質調整來接近，但不保證完全吻合。
- **GUID 不一定通用**：Logo GUID `7BB28B99-61BB-11D5-9A5D-0090273FC14D` 適用大多數 AMI BIOS，但不是所有主機板都用這個 GUID，找不到的話要自己用 UEFITool GUI 找。
- **不支援 Secure Boot**：開啟 Secure Boot 的系統可能拒絕被修改過的 BIOS。

**比較安全的做法**（但這個腳本沒實作）是用 UEFITool 0.28 GUI 的 Replace body 功能，它會正確處理 checksum。

---

## 出事了怎麼辦

如果刷完開不了機，用 BIOS 備份還原：

```bash
sudo flashrom --programmer internal -w original_bios.bin
```

如果連這個都不行，就需要**外部燒錄器（CH341A 之類的）**直接對 BIOS 晶片燒錄。

---

## 測試環境

- OS：Debian 13 (Linux 6.12)
- 主機板：MSI MS-7C31
- BIOS：AMI UEFI

其他環境**未測試**，自行承擔風險。
