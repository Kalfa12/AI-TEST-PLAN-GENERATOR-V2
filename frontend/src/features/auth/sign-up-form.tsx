import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { writeTokens } from "@/lib/auth/storage";
import { registerAccount } from "./api";

const schema = z
  .object({
    displayName: z.string().trim().min(2, "Enter your name"),
    email: z.string().trim().email("Enter a valid email"),
    password: z.string().min(8, "Use at least 8 characters"),
    confirmPassword: z.string().min(1, "Confirm your password"),
  })
  .refine((values) => values.password === values.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

type FormValues = z.infer<typeof schema>;

export function SignUpForm() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      displayName: "",
      email: "",
      password: "",
      confirmPassword: "",
    },
  });

  const onSubmit = async (values: FormValues) => {
    setServerError(null);
    try {
      const tokens = await registerAccount(
        values.email,
        values.displayName,
        values.password,
      );
      writeTokens({ access: tokens.access_token, refresh: tokens.refresh_token });
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
      navigate({ to: "/projects" });
    } catch (err) {
      if (isAxiosError(err) && err.response?.status === 409) {
        setServerError("An account with this email already exists.");
        return;
      }
      setServerError("Could not create your account. Please try again.");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="flex items-center gap-2">
            <img src="/sigmaxis-logo.png" alt="Sigmaxis" className="h-8 w-8 object-contain" />
            <CardTitle>Create account</CardTitle>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            AI Test Plan Generator
          </p>
        </CardHeader>
        <CardBody>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <div className="space-y-1">
              <label htmlFor="displayName" className="text-sm font-medium">
                Name
              </label>
              <Input
                id="displayName"
                type="text"
                autoComplete="name"
                {...register("displayName")}
              />
              {errors.displayName && (
                <p className="text-xs text-destructive">{errors.displayName.message}</p>
              )}
            </div>
            <div className="space-y-1">
              <label htmlFor="email" className="text-sm font-medium">
                Email
              </label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                {...register("email")}
              />
              {errors.email && (
                <p className="text-xs text-destructive">{errors.email.message}</p>
              )}
            </div>
            <div className="space-y-1">
              <label htmlFor="password" className="text-sm font-medium">
                Password
              </label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                {...register("password")}
              />
              {errors.password && (
                <p className="text-xs text-destructive">{errors.password.message}</p>
              )}
            </div>
            <div className="space-y-1">
              <label htmlFor="confirmPassword" className="text-sm font-medium">
                Confirm password
              </label>
              <Input
                id="confirmPassword"
                type="password"
                autoComplete="new-password"
                {...register("confirmPassword")}
              />
              {errors.confirmPassword && (
                <p className="text-xs text-destructive">
                  {errors.confirmPassword.message}
                </p>
              )}
            </div>
            {serverError && <p className="text-sm text-destructive">{serverError}</p>}
            <Button type="submit" disabled={isSubmitting} className="w-full">
              {isSubmitting ? "Creating account..." : "Create account"}
            </Button>
            <Link
              to="/"
              className="inline-flex h-10 w-full items-center justify-center rounded-md border border-border bg-transparent px-4 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              Return to home page
            </Link>
          </form>
          <p className="mt-4 text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link to="/login" className="font-medium text-primary hover:underline">
              Sign in
            </Link>
          </p>
        </CardBody>
      </Card>
    </div>
  );
}
