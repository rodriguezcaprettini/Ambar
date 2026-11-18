-- =====================================================================
-- ÁMBAR · Configuración de Supabase (pegar completo en SQL Editor → Run)
-- Crea: códigos de invitación, registro restringido por código y
-- almacenamiento privado para los datos de la terminal.
-- =====================================================================

-- 1) Tabla de códigos de invitación ------------------------------------
create table if not exists public.invite_codes (
  code        text primary key,                 -- el código que entregas (ej. AMBAR-FONDO-X)
  max_uses    integer not null default 1,       -- cuántas cuentas puede crear
  uses        integer not null default 0,       -- cuántas ya creó
  expires_at  timestamptz,                      -- vencimiento (vacío = no vence)
  active      boolean not null default true,    -- false = desactivado
  note        text,                             -- para quién es
  created_at  timestamptz not null default now()
);

-- Registro de quién usó cada código
create table if not exists public.invite_redemptions (
  id          bigserial primary key,
  code        text not null references public.invite_codes(code),
  user_id     uuid,
  email       text,
  redeemed_at timestamptz not null default now()
);

-- Nadie puede leer ni escribir estas tablas desde la página web.
-- Solo tú (desde el panel de Supabase) y el sistema de registro.
alter table public.invite_codes       enable row level security;
alter table public.invite_redemptions enable row level security;
revoke all on public.invite_codes, public.invite_redemptions from anon, authenticated;

-- 2) Regla de registro: solo con código válido --------------------------
-- Supabase la ejecuta ANTES de crear cada cuenta. Si el código no es
-- válido, la cuenta no se crea.
create or replace function public.ambar_validar_codigo(event jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_code  text := upper(trim(coalesce(event->'user'->'user_metadata'->>'invite_code', '')));
  v_email text := event->'user'->>'email';
  v_uid   uuid := nullif(event->'user'->>'id', '')::uuid;
  v_ok    text;
begin
  if v_code = '' then
    return jsonb_build_object('error', jsonb_build_object(
      'http_code', 403, 'message', 'Se requiere un código de invitación.'));
  end if;

  -- Consume un uso del código solo si está activo, vigente y con usos disponibles
  update public.invite_codes
     set uses = uses + 1
   where code = v_code
     and active
     and (expires_at is null or expires_at > now())
     and uses < max_uses
  returning code into v_ok;

  if v_ok is null then
    return jsonb_build_object('error', jsonb_build_object(
      'http_code', 403, 'message', 'Código de invitación inválido, vencido o agotado.'));
  end if;

  insert into public.invite_redemptions(code, user_id, email) values (v_code, v_uid, v_email);
  return '{}'::jsonb;   -- permitido
end;
$$;

-- Permisos para que el sistema de cuentas de Supabase pueda usar la regla
grant usage on schema public to supabase_auth_admin;
grant execute on function public.ambar_validar_codigo(jsonb) to supabase_auth_admin;
grant select, update on public.invite_codes to supabase_auth_admin;
grant insert on public.invite_redemptions to supabase_auth_admin;
grant usage, select on sequence public.invite_redemptions_id_seq to supabase_auth_admin;
revoke execute on function public.ambar_validar_codigo(jsonb) from anon, authenticated, public;

-- 3) Almacenamiento privado para los datos de la terminal ---------------
insert into storage.buckets (id, name, public)
values ('ambar-data', 'ambar-data', false)
on conflict (id) do update set public = false;

-- Solo usuarios con sesión iniciada pueden leer los datos
drop policy if exists "ambar: lectura usuarios con sesion" on storage.objects;
create policy "ambar: lectura usuarios con sesion"
  on storage.objects for select
  to authenticated
  using (bucket_id = 'ambar-data');

-- 4) Tus primeros códigos (cámbialos a tu gusto) ------------------------
insert into public.invite_codes (code, max_uses, note) values
  ('AMBAR-SEBASTIAN', 1,  'Cuenta del desarrollador'),
  ('AMBAR-PRUEBA',    5,  'Pruebas con amigos')
on conflict (code) do nothing;

-- =====================================================================
-- CÓMO CREAR MÁS CÓDIGOS (copiar, cambiar y ejecutar en SQL Editor):
--   insert into public.invite_codes (code, max_uses, expires_at, note)
--   values ('AMBAR-FONDO-X', 3, '2027-01-31', 'Equipo del Fondo X');
-- VER QUIÉN USÓ CADA CÓDIGO:
--   select * from public.invite_redemptions order by redeemed_at desc;
-- DESACTIVAR UN CÓDIGO:
--   update public.invite_codes set active = false where code = 'AMBAR-PRUEBA';
-- =====================================================================
