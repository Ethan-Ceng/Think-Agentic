```shell
  New-Item -ItemType Directory -Force .\llmops\backups
  $ts = Get-Date -Format "yyyyMMdd-HHmmss"
  docker exec llmops-db pg_dump -U postgres -d llmops -Fc -f /tmp/llmops-$ts.dump
  docker cp "llmops-db:/tmp/llmops-$ts.dump" ".\docs\backups\llmops-$ts.dump"

  备份文件会在：

  llmops\backups\llmops-时间戳.dump

  注意两点：

  - 这个备份会包含账号、应用配置、任务记录、对话、工具/API 配置等测试数据，别提交到 git。
  - 如果后续给别人用，最好先做脱敏；自己本地回归测试用没问题。

  恢复到测试库可以用：

  docker cp .\docs\backups\llmops-20260605-161900.dump llmops-db:/tmp/llmops-test.dump
  docker exec llmops-db createdb -U postgres llmops_test
  docker exec llmops-db pg_restore -U postgres -d llmops_test --clean --if-exists /tmp/llmops-test.dump
```