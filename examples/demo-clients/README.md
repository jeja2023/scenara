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

The examples never print the API token. The Python example demonstrates image upload through the shortcut API; the Node example demonstrates a Run for an already registered media asset or source.
