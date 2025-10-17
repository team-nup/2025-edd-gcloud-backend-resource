# CLAUDE.md

このファイルはClaude Code等のAIアシスタントがプロジェクトに貢献する際のガイドラインです。

## プロジェクト概要

FastAPIベースのGoogle Cloud Run バックエンドサービス。
2025 EDD (Employment Development Department) ハッカソン向けの画像分析APIを提供。

## アーキテクチャ原則

### 責務分離の厳守

このプロジェクトは明確な3層アーキテクチャを採用しています。**新しいコードは必ずこの構造に従うこと。**

```
app/
├── api/routers/      # HTTPエンドポイント層（ルーティング、バリデーション）
├── services/         # ビジネスロジック層（外部API連携、データ処理）
├── models/           # データモデル層（Pydanticスキーマ）
└── main.py           # アプリケーションエントリーポイント
```

### 各層の責務

#### 1. **app/api/routers/** - APIルーター層
- **責務**: HTTPリクエスト/レスポンスのハンドリング
- **含むべき処理**:
  - FastAPI ルーターの定義 (`APIRouter`)
  - エンドポイント関数 (`@router.get`, `@router.post`)
  - リクエストバリデーション（サイズ、形式チェック）
  - HTTPステータスコードの決定
  - 依存性注入 (`Depends`)
- **含むべきでない処理**:
  - 外部APIの直接呼び出し
  - 複雑なビジネスロジック
  - データ変換処理

**例**: `app/api/routers/gemini.py`
```python
@router.post("/analyze", response_model=GeminiAnalyzeResponse)
async def analyze_image(
    file: UploadFile = File(...),
    prompt: str = Form(...),
) -> GeminiAnalyzeResponse:
    # バリデーションのみ実施
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="画像ファイルのみ")

    # ビジネスロジックはserviceに委譲
    return await gemini_service.analyze_image(file, prompt)
```

#### 2. **app/services/** - サービス層
- **責務**: ビジネスロジックと外部API連携
- **含むべき処理**:
  - 外部API (Gemini, Vision API) の呼び出し
  - リトライロジック、エラーハンドリング
  - データ変換・加工
  - キャッシング (`@lru_cache`)
  - 詳細なロギング
- **含むべきでない処理**:
  - HTTPリクエスト/レスポンスの直接処理
  - ルーティング定義

**例**: `app/services/gemini_service.py`
```python
async def analyze_image(file: UploadFile, prompt: str) -> GeminiAnalyzeResponse:
    client = get_gemini_client()

    # リトライロジック付きAPI呼び出し
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(...)
            return GeminiAnalyzeResponse(result=response.text)
        except Exception as e:
            if "429" in str(e):
                time.sleep(RETRY_DELAY * (2**attempt))
                continue
            raise
```

#### 3. **app/models/** - データモデル層
- **責務**: データ構造の定義
- **含むべき処理**:
  - Pydanticモデルの定義
  - バリデーションルール (`Field`)
  - レスポンススキーマ
- **含むべきでない処理**:
  - ビジネスロジック
  - API呼び出し

**例**: `app/models/gemini.py`
```python
class GeminiAnalyzeResponse(BaseModel):
    result: str = Field(..., description="AI分析結果テキスト")
    status: str = Field(default="success", description="処理ステータス")
```

## 新機能追加時のルール

### 必須手順

1. **モデル定義** (`app/models/`) - 新しいリクエスト/レスポンス型を定義
2. **サービス実装** (`app/services/`) - ビジネスロジックと外部API連携
3. **ルーター追加** (`app/api/routers/`) - エンドポイント定義
4. **メインに登録** (`app/main.py`) - `app.include_router()`で登録

### 禁止事項

- ❌ ルーター内で外部APIを直接呼び出す
- ❌ サービス層でFastAPIのHTTPException以外の例外を発生させる
- ❌ 既存のディレクトリ構造外にファイルを作成する
- ❌ `app/utils/`, `app/helpers/` などの曖昧なディレクトリを作る

## 既存機能の概要

### 1. Health Check API (`app/api/routers/health.py`)
- **エンドポイント**:
  - `GET /api/v1/health/` - 基本ヘルスチェック
  - `GET /api/v1/health/liveness` - Cloud Run liveness probe
  - `GET /api/v1/health/readiness` - Cloud Run readiness probe
  - `GET /api/v1/health/detailed` - 詳細システム情報
- **責務**: サービスの稼働状態確認

### 2. Vision API (`app/api/routers/vision.py` + `app/services/vision_service.py`)
- **エンドポイント**:
  - `POST /api/v1/vision/web-detection` - Cloud Vision Web Detection
  - `GET /api/v1/vision/health` - Vision API接続確認
- **機能**: Base64画像のバッチ解析
- **外部API**: Google Cloud Vision API

### 3. Gemini API (`app/api/routers/gemini.py` + `app/services/gemini_service.py`)
- **エンドポイント**:
  - `POST /api/v1/gemini/analyze` - Gemini 2.5 Pro画像分析
  - `GET /api/v1/gemini/health` - Gemini API接続確認
- **機能**:
  - 画像 + プロンプト → AI分析結果
  - 429エラー時の自動リトライ（Exponential Backoff: 2秒→4秒→8秒）
  - 最大20MB画像サポート
  - プロンプト長制限なし（1M tokens対応）
- **外部API**: Vertex AI Gemini 2.5 Pro (global endpoint)

## 重要な実装パターン

### エラーハンドリング

```python
# Service層
try:
    result = external_api_call()
    logger.info(f"Success: {result}")
    return result
except Exception as e:
    logger.error(f"Error: {e}")
    raise HTTPException(status_code=500, detail=f"API Error: {e!s}") from e
```

### リトライロジック

429エラー (RESOURCE_EXHAUSTED) に対してのみリトライ実施:

```python
for attempt in range(MAX_RETRIES):
    try:
        return api_call()
    except Exception as e:
        if "429" in str(e) and attempt < MAX_RETRIES - 1:
            time.sleep(INITIAL_RETRY_DELAY * (2**attempt))
            continue
        raise
```

### 依存性注入

```python
# Router層で依存性を定義
def get_service() -> Service:
    return Service()

@router.post("/endpoint")
async def endpoint(service: Service = Depends(get_service)):
    return await service.process()
```

## 環境変数

- `PORT` - サーバーポート (default: 8080)
- `PYTHON_VERSION` - Pythonバージョン情報
- `GOOGLE_CLOUD_PROJECT` - GCPプロジェクトID
- `VERTEX_AI_LOCATION` - Vertex AIリージョン (default: "global")

## デプロイメント

### ローカル開発
```bash
uv sync --dev
uv run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### コード品質チェック
```bash
uv run ruff check app/          # Lint
uv run ruff check --fix app/    # Auto-fix
uv run ruff format app/         # Format
```

### Cloud Runデプロイ
```bash
./deploy.sh [PROJECT_ID] [REGION] [SERVICE_NAME]
```

## コーディング規約

### Python
- **スタイル**: Ruff (line-length: 88)
- **型ヒント**: 必須 (`def func() -> ReturnType:`)
- **非同期関数**: I/O処理は`async/await`を使用
- **ロギング**: `logger.info/error`で詳細を記録

### API設計
- **レスポンス**: 常にPydanticモデルを使用
- **エラー**: `HTTPException`で統一
- **バリデーション**: Router層で実施
- **ドキュメント**: Docstringを必ず記述

### 命名規則
- **ファイル**: スネークケース (`gemini_service.py`)
- **クラス**: パスカルケース (`GeminiAnalyzeResponse`)
- **関数/変数**: スネークケース (`analyze_image()`)
- **定数**: 大文字スネークケース (`MAX_FILE_SIZE`)

## パフォーマンス考慮事項

### 現在の制限
- **ファイルサイズ**: 20MB (Gemini API上限に準拠)
- **プロンプト長**: 制限なし (Gemini 2.5 Proは1M tokens対応)
- **タイムアウト**: 300秒 (Cloud Run設定)
- **同時実行数**: 80 (Cloud Run設定)
- **メモリ**: 1Gi (Cloud Run設定)

### リトライ設定
- **最大試行回数**: 3回
- **初期遅延**: 2秒
- **バックオフ**: Exponential (2秒 → 4秒 → 8秒)

## テスト

### ヘルスチェック
```bash
curl https://[SERVICE_URL]/api/v1/health
```

### ローカルテスト
```bash
./local-test.sh          # ビルド + 実行 + テスト
./local-test.sh build    # Dockerビルドのみ
./local-test.sh test     # テストのみ
```

## トラブルシューティング

### 429 RESOURCE_EXHAUSTED エラー
- **原因**: Gemini APIクォータ超過
- **対策**:
  - リトライロジックで自動回復（最大3回）
  - `VERTEX_AI_LOCATION=global`で高いクォータを使用

### メモリ不足
- **原因**: 大きな画像のbase64変換
- **対策**:
  - 画像サイズを20MB以下に制限
  - 必要に応じてCloud Runメモリを増やす (`deploy.sh`の`MEMORY`変数)

## AIアシスタントへの指示

このプロジェクトに貢献する際は:

1. **必ず既存の3層構造に従う** - 新しい層やutilsディレクトリは作らない
2. **責務を混在させない** - 各層の役割を厳守
3. **既存のパターンを踏襲** - 既存コードのスタイルを確認してから実装
4. **変更前に構造を確認** - `app/`配下の構造を理解してから作業
5. **テスト可能性を保つ** - 依存性注入を活用

これらのガイドラインに従うことで、保守性が高く、拡張しやすいコードベースを維持できます。
