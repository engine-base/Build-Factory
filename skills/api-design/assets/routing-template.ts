// ルーティング定義テンプレート（Next.js App Router / Express想定）
// このファイルはapi-designスキルの出力を元に自動生成される

// ---- API Routes (Next.js App Router) ----

// app/api/auth/login/route.ts
export const authRoutes = {
  login: "POST /api/auth/login",
  logout: "POST /api/auth/logout",
  refresh: "POST /api/auth/refresh",
} as const;

// app/api/users/route.ts
export const userRoutes = {
  me: "GET /api/users/me",
  updateMe: "PATCH /api/users/me",
} as const;

// app/api/resources/route.ts
export const resourceRoutes = {
  list: "GET /api/resources",
  create: "POST /api/resources",
  show: "GET /api/resources/:id",
  update: "PATCH /api/resources/:id",
  delete: "DELETE /api/resources/:id",
} as const;

// ---- TypeScript型定義 ----

export type ResourceStatus = "draft" | "published" | "archived";

export interface User {
  id: string;
  email: string;
  name: string;
  createdAt: Date;
}

export interface Resource {
  id: string;
  title: string;
  content: string;
  status: ResourceStatus;
  createdAt: Date;
  updatedAt: Date;
}

export interface PaginationMeta {
  total: number;
  page: number;
  perPage: number;
  totalPages: number;
}

export interface PaginatedResponse<T> {
  data: T[];
  meta: PaginationMeta;
}

// ---- Error types ----

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Array<{ field: string; message: string }>;
  };
}
