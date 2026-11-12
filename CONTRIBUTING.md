# Contributing

1. Create a feature branch; do not commit directly to `main`.
2. Keep the shared Django API and database contract consistent across all four portals.
3. Do not introduce destructive migrations or delete existing user/order data.
4. Run backend checks/tests and all four frontend builds before opening a pull request.
5. Never commit secrets, local databases, user uploads, `node_modules`, or generated build folders.
6. Describe which portal(s) and API behavior are affected in each pull request.
