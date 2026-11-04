-- Local AI Search: métricas anônimas, leads voluntários e benchmarks da comunidade.
-- As tabelas ficam no schema "privado" (fora da API). O site e o app só chamam três funções públicas que validam
-- e gravam; ninguém de fora consegue LER nada. Sem cookies, sem IP. Idempotente: pode rodar mais de uma vez.

create schema if not exists privado;
revoke all on schema privado from public, anon, authenticated;

create table if not exists privado.eventos (
  id bigint generated always as identity primary key,
  criado timestamptz not null default now(),
  tipo text not null,                 -- pagina, aba, copiar, loja, download, apoio, lead, uso, radar
  aba text,
  sessao text,                        -- id aleatório por aba do navegador (sessionStorage), sem cookie
  novo boolean,                       -- primeira visita neste navegador
  origem text,                        -- só o domínio de quem indicou (referrer)
  utm_source text, utm_medium text, utm_campaign text,
  dispositivo text,                   -- celular | computador
  idioma text,
  host text,                          -- domínio do site (separa produção de pré-visualização)
  dados jsonb not null default '{}'::jsonb
);
create index if not exists eventos_criado_idx on privado.eventos (criado);
create index if not exists eventos_tipo_idx on privado.eventos (tipo, criado);

create table if not exists privado.leads (
  id bigint generated always as identity primary key,
  criado timestamptz not null default now(),
  email text not null,
  interesse text not null default 'novidades',   -- novidades | alerta-hardware
  hardware text,                                 -- ex.: "GeForce RTX 4070 · 32 GB" (para o alerta de modelo novo)
  origem text,                                   -- site | app | aba de onde veio
  consentimento text not null,                   -- texto exato aceito pela pessoa
  descadastrado boolean not null default false
);
create unique index if not exists leads_email_idx on privado.leads (lower(email));

create table if not exists privado.benchmarks (
  id bigint generated always as identity primary key,
  criado timestamptz not null default now(),
  versao_app text, protocolo text, nivel text,
  modelo text not null, digest text, quant text, bytes bigint,
  hardware jsonb not null,            -- placa, VRAM, RAM, CPU, SO (sem nome da máquina)
  resultado jsonb not null            -- notas por função e por teste, tok/s, contexto que cabe na GPU
);
create index if not exists benchmarks_modelo_idx on privado.benchmarks (modelo, criado);

-- ---------------------------------------------------------------- funções públicas (únicas portas de entrada)
create or replace function public.registrar_evento(
  p_tipo text, p_aba text default null, p_sessao text default null, p_novo boolean default null,
  p_origem text default null, p_utm jsonb default '{}'::jsonb, p_dispositivo text default null,
  p_idioma text default null, p_host text default null, p_dados jsonb default '{}'::jsonb)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if p_tipo is null or p_tipo not in ('pagina','aba','copiar','loja','download','apoio','lead','uso','radar','calculadora') then
    raise exception 'tipo inválido';
  end if;
  if octet_length(coalesce(p_dados,'{}'::jsonb)::text) > 2000 or octet_length(coalesce(p_utm,'{}'::jsonb)::text) > 600 then
    raise exception 'dados grandes demais';
  end if;
  insert into privado.eventos (tipo, aba, sessao, novo, origem, utm_source, utm_medium, utm_campaign, dispositivo, idioma, host, dados)
  values (p_tipo, left(p_aba, 40), left(p_sessao, 40), p_novo, left(p_origem, 120),
          left(p_utm->>'source', 80), left(p_utm->>'medium', 80), left(p_utm->>'campaign', 120),
          left(p_dispositivo, 20), left(p_idioma, 20), left(p_host, 120), coalesce(p_dados, '{}'::jsonb));
end $$;

create or replace function public.registrar_lead(
  p_email text, p_consentimento text, p_interesse text default 'novidades', p_hardware text default null, p_origem text default null)
returns text language plpgsql security definer set search_path = '' as $$
declare v_email text := lower(trim(p_email));
begin
  if v_email is null or length(v_email) > 254 or v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]{2,}$' then
    raise exception 'e-mail inválido';
  end if;
  if p_consentimento is null or length(p_consentimento) < 10 or length(p_consentimento) > 600 then
    raise exception 'consentimento ausente';
  end if;
  if coalesce(p_interesse,'novidades') not in ('novidades','alerta-hardware') then
    raise exception 'interesse inválido';
  end if;
  insert into privado.leads (email, interesse, hardware, origem, consentimento)
  values (v_email, coalesce(p_interesse,'novidades'), left(p_hardware, 120), left(p_origem, 60), p_consentimento)
  on conflict (lower(email)) do nothing;
  if found then return 'ok'; end if;
  return 'ja_cadastrado';
end $$;

create or replace function public.enviar_benchmark(p jsonb)
returns text language plpgsql security definer set search_path = '' as $$
begin
  if p is null or octet_length(p::text) > 20000 then raise exception 'envio inválido'; end if;
  if coalesce(p->>'modelo','') = '' or jsonb_typeof(p->'hardware') <> 'object' or jsonb_typeof(p->'resultado') <> 'object' then
    raise exception 'faltam modelo, hardware ou resultado';
  end if;
  insert into privado.benchmarks (versao_app, protocolo, nivel, modelo, digest, quant, bytes, hardware, resultado)
  values (left(p->>'versao_app',20), left(p->>'protocolo',20), left(p->>'nivel',20), left(p->>'modelo',160), left(p->>'digest',80),
          left(p->>'quant',30), nullif(p->>'bytes','')::bigint, p->'hardware', p->'resultado');
  return 'ok';
end $$;

revoke all on function public.registrar_evento(text,text,text,boolean,text,jsonb,text,text,text,jsonb) from public;
revoke all on function public.registrar_lead(text,text,text,text,text) from public;
revoke all on function public.enviar_benchmark(jsonb) from public;
grant execute on function public.registrar_evento(text,text,text,boolean,text,jsonb,text,text,text,jsonb) to anon, authenticated;
grant execute on function public.registrar_lead(text,text,text,text,text) to anon, authenticated;
grant execute on function public.enviar_benchmark(jsonb) to anon, authenticated;
