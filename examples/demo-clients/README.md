# Scenara 景枢 SDK 示例

两个示例均使用公开 `/api/v1` 契约与受支持的 Scenara SDK。

```bash
export SCENARA_BASE_URL="https://scenara.internal.example"
export SCENARA_TENANT_ID="tenant-a"
export SCENARA_PROJECT_ID="project-a"
export SCENARA_API_TOKEN="..."

python examples/demo-clients/python_demo_client.py --dry-run
python examples/demo-clients/python_demo_client.py --image samples/document.png --domain ocr

node examples/demo-clients/node_demo_client.js --dry-run
node examples/demo-clients/node_demo_client.js --asset-id ast_example --domain portrait
```

示例脚本绝不会打印 API 令牌。Python 示例演示通过快捷 API 进行图片上传解析；Node 示例演示针对已登记的媒体资产或媒体源创建并轮询 Run 任务。
