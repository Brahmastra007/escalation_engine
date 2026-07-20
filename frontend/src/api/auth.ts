import client from "./client";
import type { LoginResponse, User } from "../types";

export async function login(
  email: string,
  password: string
): Promise<LoginResponse> {
  const response = await client.post<LoginResponse>("/auth/login", {
    email,
    password,
  });
  return response.data;
}

export async function getMe(): Promise<User> {
  const response = await client.get<User>("/auth/me");
  return response.data;
}
