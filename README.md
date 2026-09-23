# ZaloProductImporter

ZaloProductImporter là công cụ CLI viết bằng Python để tạo hàng loạt sản phẩm trong Zalo Product Catalog từ file JSON, thông qua API nội bộ của Zalo Web.

Tham khảo một phần cách làm từ dự án [Its-VrxxDev/zlapi](https://github.com/Its-VrxxDev/zlapi).

> Lưu ý: Đây là API nội bộ của Zalo Web, không phải API chính thức. Mọi trách nhiệm xảy ra khi tài khoản bị khoá/spam tự chịu trách nhiệm.

## Cài đặt

Tạo môi trường ảo và cài dependency:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Nếu không cài package ở chế độ editable, có thể chạy bằng:

```bash
PYTHONPATH=src python -m zalo_product_importer --help
```

Sau khi đã cài editable package, có thể chạy trực tiếp:

```bash
ZaloProductImporter --help
```

## Cấu hình

1. Sao chép nội dung từ `config.example.json` sang `config.json`.
2. Điền các thông tin cần thiết:
   - `imei`: giá trị `z_uuid` hoặc `sh_z_uuid` lấy từ `localStorage` của `chat.zalo.me`.
   - `cookies`: cookie hiện tại của đúng tài khoản Zalo Web, tối thiểu nên có `zpsid` và `zpw_sek`.
   - `endpoints`: giữ mặc định nếu API Zalo Web chưa thay đổi.
     - `product_photo_upload`: endpoint upload ảnh local trước khi tạo sản phẩm.
   - `batch.delay_seconds`: thời gian chờ giữa các lần tạo sản phẩm.
   - `batch.stop_on_quota_error`: dừng batch khi gặp lỗi giới hạn số lượng sản phẩm.

`config.json` chứa cookie thật, chỉ nên lưu trên máy cá nhân và không commit lên Git.

Extension lấy `imei` và cookies Zalo Web: [taphoaneil/get-cookies-zalo](https://github.com/taphoaneil/get-cookies-zalo).

## File sản phẩm

`products.json` là một mảng JSON. Mỗi phần tử tương ứng với một sản phẩm cần tạo:

```json
[
  {
    "product_name": "Sản phẩm mẫu 001",
    "price": "100000",
    "description": "Mô tả ngắn cho sản phẩm mẫu.",
    "product_photos": [
      "images/san-pham-001.jpg",
      "https://example.com/anh-da-co-san.jpg"
    ],
    "catalog_id": "paste_catalog_id_for_this_product"
  }
]
```

Quy tắc dữ liệu hiện tại:

- `product_name` là bắt buộc.
- `price` là chuỗi chỉ gồm chữ số hoặc để rỗng.
- `description` mặc định là chuỗi rỗng nếu không truyền.
- `product_photos` là mảng ảnh, tối đa 5 ảnh. Mỗi phần tử có thể là URL `http/https` hoặc đường dẫn file ảnh local.
- Khi chạy `create`, URL ảnh sẽ được tải về file tạm, sau đó mọi ảnh đều được upload lại lên Zalo, lấy `normalUrl`, rồi đưa URL Zalo đó vào payload tạo sản phẩm.
- Đường dẫn ảnh local tương đối được tính từ thư mục chứa file JSON sản phẩm.
- `catalog_id` là bắt buộc trên từng sản phẩm. Dùng lệnh `catalogs` để lấy ID danh mục.

## Lệnh sử dụng

Kiểm tra cấu hình và file sản phẩm:

```bash
PYTHONPATH=src python -m zalo_product_importer validate --input products.json
```

Lấy danh sách danh mục và `catalog_id`:

```bash
PYTHONPATH=src python -m zalo_product_importer catalogs
```

Ví dụ output:

```text
catalog_id            catalog_name
--------------------  ------------
ead3d7f9dfbc36e26fad  Test 1
fd2cd434c4712d2f7460  Test 2
```

Sao chép giá trị ở cột `catalog_id` vào từng sản phẩm trong `products.json` để chọn danh mục mà sản phẩm được tải lên.

Chạy dry-run để tạo payload và kiểm tra dữ liệu, không gọi API tạo sản phẩm:

```bash
PYTHONPATH=src python -m zalo_product_importer create --input products.json --dry-run
```

Tạo sản phẩm thật:

```bash
PYTHONPATH=src python -m zalo_product_importer create --input products.json
```

Kết quả mỗi lần tạo được ghi vào:

```text
results/YYYYMMDD-HHMMSS-create-result.json
```

## Giấy phép

MIT License, copyright (c) 2026 @taphoaneil.

Xem chi tiết trong `LICENSE`.
