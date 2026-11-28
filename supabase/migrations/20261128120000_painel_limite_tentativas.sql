-- Painel: limite de tentativas de senha.
--
-- Antes, cada senha errada custava só 1 s (pg_sleep) e não ficava registrada: dava para tentar sem parar.
-- Agora painel_resumo e painel_acao passam por privado.painel_portao, que:
--   • bloqueia por 15 min quem errou 5 vezes (por origem: o hash do IP que o /api/coleta manda no cabeçalho
--     x-cliente-ip; quem chama o banco direto, sem o intermediário, cai todo na mesma origem "?");
--   • bloqueia todo mundo por 1 h se houver 30 erros no total nesse período (ataque vindo de muitos IPs);
--   • zera as tentativas da origem quando a senha está certa e apaga registros com mais de 1 dia.
-- Os erros voltam como {"erro": "..."} em vez de exceção: uma exceção desfaria a transação e apagaria o próprio
-- registro da tentativa. O /api/coleta transforma {"erro"} em HTTP 401/429 para o painel mostrar a mensagem.
-- As funções antigas continuam existindo, em privado, só para uso interno (ninguém de fora as chama).

create table if not exists privado.painel_tentativas (
  id bigserial primary key,
  criado timestamptz not null default now(),
  origem text not null
);
create index if not exists painel_tentativas_criado_idx on privado.painel_tentativas (criado);
create index if not exists painel_tentativas_origem_idx on privado.painel_tentativas (origem, criado);
revoke all on privado.painel_tentativas from public, anon, authenticated;
revoke all on sequence privado.painel_tentativas_id_seq from public, anon, authenticated;

-- Devolve null se a senha confere; senão, o motivo da recusa.
create or replace function privado.painel_portao(p_senha text)
returns text language plpgsql volatile security definer set search_path = '' as $$
declare
  v_cab text := current_setting('request.headers', true);
  v_origem text := '?';
begin
  begin
    v_origem := coalesce(nullif(left(v_cab::json ->> 'x-cliente-ip', 64), ''), '?');
  exception when others then v_origem := '?';   -- sem cabeçalhos (chamada fora do PostgREST) ou JSON inválido
  end;

  delete from privado.painel_tentativas where criado < now() - interval '1 day';

  if (select count(*) from privado.painel_tentativas where origem = v_origem and criado > now() - interval '15 minutes') >= 5 then
    return 'Muitas tentativas. Tente de novo em 15 minutos.';
  end if;
  if (select count(*) from privado.painel_tentativas where criado > now() - interval '1 hour') >= 30 then
    return 'Painel bloqueado por excesso de tentativas. Tente de novo em 1 hora.';
  end if;

  if p_senha is null or length(p_senha) > 512 or not exists (select 1 from privado.painel_acesso where senha = p_senha) then
    insert into privado.painel_tentativas (origem) values (v_origem);
    return 'Senha incorreta.';
  end if;

  delete from privado.painel_tentativas where origem = v_origem;
  return null;
end $$;
revoke all on function privado.painel_portao(text) from public, anon, authenticated;

-- As versões atuais saem do esquema público e viram internas.
alter function public.painel_resumo(text, integer) set schema privado;
alter function privado.painel_resumo(text, integer) rename to painel_resumo_interno;
revoke all on function privado.painel_resumo_interno(text, integer) from public, anon, authenticated;

alter function public.painel_acao(text, text, text) set schema privado;
alter function privado.painel_acao(text, text, text) rename to painel_acao_interno;
revoke all on function privado.painel_acao_interno(text, text, text) from public, anon, authenticated;

-- Mesmas assinaturas de antes: o painel e o intermediário não mudam a chamada.
create or replace function public.painel_resumo(p_senha text, p_dias int default 30)
returns jsonb language plpgsql volatile security definer set search_path = '' as $$
declare v_erro text := privado.painel_portao(p_senha);
begin
  if v_erro is not null then return jsonb_build_object('erro', v_erro); end if;
  return privado.painel_resumo_interno(p_senha, p_dias);
end $$;
revoke all on function public.painel_resumo(text, int) from public;
grant execute on function public.painel_resumo(text, int) to anon, authenticated;

create or replace function public.painel_acao(p_senha text, p_acao text, p_valor text default null)
returns jsonb language plpgsql volatile security definer set search_path = '' as $$
declare v_erro text := privado.painel_portao(p_senha);
begin
  if v_erro is not null then return jsonb_build_object('erro', v_erro); end if;
  return privado.painel_acao_interno(p_senha, p_acao, p_valor);
end $$;
revoke all on function public.painel_acao(text, text, text) from public;
grant execute on function public.painel_acao(text, text, text) to anon, authenticated;
