import logging
import os
import time
from functools import lru_cache

from fastapi import HTTPException, UploadFile
from google import genai
from google.genai import types

from app.models.gemini import GeminiAnalyzeResponse

logger = logging.getLogger(__name__)

# リトライ設定
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 2  # 秒


@lru_cache(maxsize=1)
def get_gemini_client() -> genai.Client:
    """
    Vertex AI経由でGemini APIクライアントを取得（キャッシュ付き）

    Returns:
        Gemini APIクライアント

    Raises:
        HTTPException: クライアント初期化エラー
    """
    try:
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT環境変数が設定されていません")

        location = os.getenv("VERTEX_AI_LOCATION")
        if not location:
            raise ValueError("VERTEX_AI_LOCATION環境変数が設定されていません")

        client = genai.Client(vertexai=True, project=project_id, location=location)

        logger.info(
            f"Gemini client initialized for project: {project_id}, location: {location}"
        )
        return client

    except Exception as e:
        logger.error(f"Gemini client initialization failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Gemini API初期化エラー: {e!s}"
        ) from e


async def analyze_image(file: UploadFile, prompt: str) -> GeminiAnalyzeResponse:
    """
    画像とプロンプトを使用してGemini 2.5 Proで分析を実行
    429 RESOURCE_EXHAUSTEDエラー時は自動リトライを実行

    Args:
        file: アップロードされた画像ファイル
        prompt: 分析用テキストプロンプト

    Returns:
        分析結果レスポンス

    Raises:
        HTTPException: Gemini API呼び出しエラー
    """
    client = get_gemini_client()

    # 画像をバイナリで読み込み
    image_bytes = await file.read()

    # ファイルポインタを先頭に戻す（必要に応じて）
    if hasattr(file.file, "seek"):
        file.file.seek(0)

    # 画像をPartに変換
    image_part = types.Part.from_bytes(
        data=image_bytes, mime_type=file.content_type or "image/jpeg"
    )

    # リトライロジック付きでGemini API呼び出し
    last_exception = None
    for attempt in range(MAX_RETRIES):
        try:
            start_time = time.time()
            logger.info(
                f"Gemini API呼び出し開始 (試行 {attempt + 1}/{MAX_RETRIES}) - "
                f"ファイル: {file.filename}, プロンプト長: {len(prompt)}文字"
            )

            # Gemini 2.5 Proを呼び出し
            response = client.models.generate_content(
                model="gemini-2.5-pro",
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=prompt), image_part],
                    )
                ],
            )

            elapsed_time = time.time() - start_time

            # レスポンステキストを取得
            result_text = (
                response.text if response.text else "分析結果を取得できませんでした"
            )

            logger.info(
                f"Gemini analysis completed successfully - "
                f"ファイル: {file.filename}, 処理時間: {elapsed_time:.2f}秒, "
                f"レスポンス長: {len(result_text)}文字"
            )

            return GeminiAnalyzeResponse(result=result_text, status="success")

        except Exception as e:
            last_exception = e
            error_str = str(e)

            # 429エラー（RESOURCE_EXHAUSTED）の場合のみリトライ
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                if attempt < MAX_RETRIES - 1:
                    # Exponential backoff: 2秒 -> 4秒 -> 8秒
                    retry_delay = INITIAL_RETRY_DELAY * (2**attempt)
                    logger.warning(
                        f"429 RESOURCE_EXHAUSTED エラー発生 (試行 {attempt + 1}/{MAX_RETRIES}) - "
                        f"{retry_delay}秒後にリトライします: {error_str}"
                    )
                    time.sleep(retry_delay)
                    continue
                else:
                    logger.error(
                        f"Gemini API 429エラー - 最大リトライ回数({MAX_RETRIES})到達: {error_str}"
                    )
            else:
                # 429以外のエラーは即座に失敗
                logger.error(
                    f"Gemini API呼び出しエラー (試行 {attempt + 1}): {error_str}"
                )
                break

    # すべてのリトライが失敗した場合
    error_detail = f"Gemini API分析エラー: {last_exception!s}"
    logger.error(f"All retries failed - {error_detail}")
    raise HTTPException(status_code=500, detail=error_detail) from last_exception


def health_check() -> bool:
    """
    Gemini API接続確認

    Returns:
        接続状態（True: 正常, False: 異常）
    """
    try:
        get_gemini_client()
        return True
    except Exception as e:
        logger.error(f"Gemini health check failed: {e}")
        return False
