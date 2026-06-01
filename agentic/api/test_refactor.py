#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试脚本 - 验证新架构的导入和基本功能
"""
import sys
import traceback


def test_imports():
    """测试所有模块导入"""
    print("=" * 80)
    print("测试模块导入...")
    print("=" * 80)

    tests = [
        ("Models", "from app.models import SessionModel, FileModel, SessionStatus"),
        ("Extensions", "from app.extensions import get_db, get_redis, get_storage"),
        ("Services", "from app.services import SessionService, AgentService"),
        ("Controllers", "from app.controllers import router"),
        ("Core", "from app.core.agent import ReActAgent"),
        ("Schemas", "from app.schemas.session import SessionResponse"),
    ]

    passed = 0
    failed = 0

    for name, import_stmt in tests:
        try:
            exec(import_stmt)
            print(f"✅ {name}: OK")
            passed += 1
        except Exception as e:
            print(f"❌ {name}: FAILED")
            print(f"   Error: {e}")
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 80)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 80)

    return failed == 0


def test_structure():
    """测试目录结构"""
    import os

    print("\n" + "=" * 80)
    print("检查目录结构...")
    print("=" * 80)

    required_dirs = [
        "app/models",
        "app/services",
        "app/controllers",
        "app/extensions",
        "app/core",
        "app/core/agent",
        "app/core/sandbox",
        "app/schemas",
    ]

    all_exist = True
    for dir_path in required_dirs:
        exists = os.path.exists(dir_path)
        status = "✅" if exists else "❌"
        print(f"{status} {dir_path}")
        if not exists:
            all_exist = False

    return all_exist


def main():
    """主函数"""
    print("\n🚀 开始测试新架构\n")

    # 测试目录结构
    structure_ok = test_structure()

    # 测试导入
    imports_ok = test_imports()

    # 总结
    print("\n" + "=" * 80)
    if structure_ok and imports_ok:
        print("🎉 所有测试通过！新架构已就绪。")
        print("\n下一步:")
        print("1. 启动服务: uvicorn app.main:app --reload")
        print("2. 访问文档: http://localhost:8000/docs")
        print("3. 测试API: http://localhost:8000/api/status")
    else:
        print("❌ 部分测试失败，请检查错误信息。")
        sys.exit(1)
    print("=" * 80)


if __name__ == "__main__":
    main()
