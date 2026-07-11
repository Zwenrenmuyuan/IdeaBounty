"""将一个已经注册的账号提升为管理员。"""

import argparse

from idea_bounty.db import SessionFactory
from idea_bounty.services.admin import promote_user_to_admin


def main() -> int:
    parser = argparse.ArgumentParser(description="将已有用户提升为管理员")
    parser.add_argument("username", help="已注册的用户名")
    args = parser.parse_args()

    with SessionFactory() as db_session:
        promoted = promote_user_to_admin(db_session, args.username)
    if not promoted:
        print("用户不存在")
        return 1
    print(f"已将用户 {args.username.strip().lower()} 提升为管理员")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
