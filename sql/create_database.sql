-- Execute no banco postgres, como administrador, uma única vez.
-- Substitua a senha abaixo pela mesma usada no .env.
-- CREATE DATABASE precisa ser executado fora de uma transação.
CREATE ROLE agendai WITH LOGIN PASSWORD 'troque_esta_senha';
CREATE DATABASE agendai OWNER agendai ENCODING 'UTF8';
