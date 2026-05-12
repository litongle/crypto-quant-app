"""
生成 ADMIN_PASSWORD_HASH。

用法（在仓库根目录跑）：
    docker compose run --rm backend python -m scripts.generate_admin_hash

会交互提示两遍密码，输出 bcrypt 哈希。把它复制到 .env 的 ADMIN_PASSWORD_HASH。
"""

import getpass
import sys

from app.core.security import hash_password


def main() -> int:
    pw1 = getpass.getpass("管理员密码：")
    if len(pw1) < 8:
        print("错误：密码至少 8 位", file=sys.stderr)
        return 1
    pw2 = getpass.getpass("再次输入：")
    if pw1 != pw2:
        print("错误：两次输入不一致", file=sys.stderr)
        return 1
    print()
    print("把下面这行复制到 .env：")
    print(f"ADMIN_PASSWORD_HASH={hash_password(pw1)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
