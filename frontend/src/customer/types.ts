export type Merchant = { id: number; shop_name: string; image?: string | null; cover_image?: string | null; description?: string; category?: string; address?: string; latitude?: string | number | null; longitude?: string | number | null; is_open: boolean; rating?: string | number; };
export type Product = { id: number; merchant: number; merchant_name?: string; name: string; category?: string; description?: string; image?: string | null; price: string | number; available: boolean; quantity?: number | null; low_stock_threshold?: number; stock_status?: 'untracked' | 'out' | 'low' | 'in'; };
export type CartLine = { product: Product; quantity: number };
export type Order = {
  id: number;
  status: string;
  merchant_name?: string;
  total: string | number;
  delivery_fee?: string | number;
  dropoff_address?: string;
  created_at?: string;
  completed_at?: string | null;
  captain_rating?: string | number | null;
  merchant_rating?: string | number | null;
  payment_method?: 'cash' | 'online';
  activities?: { id: number; event: string; from_status: string; to_status: string; actor_name: string; created_at: string }[];
  my_ratings?: { target_type: 'captain' | 'merchant'; score: number; comment: string }[];
};
