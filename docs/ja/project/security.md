# セキュリティ

[English](../../en/project/security.md)

Dashboard は loopback address のみに bind し、すべての API request に暗号学的に安全な random token を要求します。Static asset はローカルに同梱され、request body の size は制限されます。Directory traversal は拒否され、restrictive な Content Security Policy が返されます。

`ui.bind_address` を loopback 以外へ変更しないでください。Configuration validation はその設定を拒否します。Export された基板 geometry と report は、機密性のある設計情報として扱ってください。

脆弱性は公開前に project maintainer へ非公開で報告してください。この source snapshot は公開 security mailbox を指定していません。配布する組織は、組織管理の連絡先を追加してください。
