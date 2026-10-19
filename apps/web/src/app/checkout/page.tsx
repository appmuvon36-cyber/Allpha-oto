import { redirect } from "next/navigation";

/**
 * Checkout is intentionally implemented inside the authenticated cart flow so
 * cart contents, address form, idempotency, and order confirmation share one
 * server-validated path. Preserve a stable direct checkout URL by routing it
 * to that existing flow instead of returning a 404.
 */
export default function CheckoutPage(): never {
  redirect("/cart");
}
