# Banner Inventory -- 109 banners (ports 9001-9110, skip 9100)

## Categories

| Categorie | Taxonomies couvertes |
|-----------|---------------------|
| RESEAU | CISC, JUNI, FORTI, PALOA, HPIL |
| SSH_TELNET | OSSH, VNC, IRC, TELNT |
| MAIL | SMTP, POP3, IMAP |
| WEB | NGINX, APACH, GRAFNA, JENK, ELAST, ZABBIX + many more |
| PROTOCOLES | FTP, MEMC, REDIS, PRXY |
| ICS_SCADA | SIEM, SCAD |
| DATABASES | MSSQL, PGSQL, MYSQL, MONGO, MARD |
| AUTRE | RDP, LDAP, IPP, Oracle, PJL, Modbus |

## Full Tracking Table

| # | ID | Tax | Port | Type | Recette | Date |
|---|-----|-----|------|------|---------|------|
| 1 | lia-cisco-ssh | CISC | 9001 | tcp_init | PASS | 2026-03-02 |
| 2 | lia-juniper-ssh | JUNI | 9002 | tcp_init | PASS | 2026-03-02 |
| 3 | lia-openssh | OSSH | 9003 | tcp_init | PASS | 2026-03-02 |
| 4 | lia-hpilo | HPIL | 9004 | tcp_init | PASS | 2026-03-02 |
| 5 | lia-vnc | VNC | 9005 | tcp_init | PASS | 2026-03-02 |
| 6 | lia-ftp | FTP | 9006 | tcp_init | PASS | 2026-03-02 |
| 7 | lia-smtp | SMTP | 9007 | tcp_init | PASS | 2026-03-02 |
| 8 | lia-pop3 | POP3 | 9008 | tcp_init | PASS | 2026-03-02 |
| 9 | lia-imap | IMAP | 9009 | tcp_init | PASS | 2026-03-02 |
| 10 | lia-telnet-fortigate | FORTI | 9010 | tcp_init | PASS | 2026-03-02 |
| 11 | lia-irc | IRC | 9011 | tcp_init | PASS | 2026-03-02 |
| 12 | lia-memcache | MEMC | 9012 | tcp_respond | PASS | 2026-03-02 |
| 13 | lia-redis | REDIS | 9013 | tcp_respond | PASS | 2026-03-02 |
| 14 | lia-nginx | NGINX | 9014 | http | PASS | 2026-03-02 |
| 15 | lia-apache | APACH | 9015 | http | PASS | 2026-03-02 |
| 16 | lia-grafana | GRAFNA | 9016 | http | PASS | 2026-03-02 |
| 17 | lia-jenkins | JENK | 9017 | http | PASS | 2026-03-02 |
| 18 | lia-elasticsearch | ELAST | 9018 | http | PASS | 2026-03-02 |
| 19 | lia-siemens-http | SIEM | 9019 | http | PASS | 2026-03-02 |
| 20 | lia-socks5 | PRXY | 9020 | hex_respond | PASS | 2026-03-02 |
| 21 | lia-paloalto | PALOA | 9021 | http | PASS | 2026-03-02 |
| 22 | lia-fortinet-ssh | FORTI | 9022 | tcp_init | PASS | 2026-03-02 |
| 23 | lia-zabbix | ZABBIX | 9023 | http | PASS | 2026-03-02 |
| 24 | lia-mssql | MSSQL | 9024 | hex_respond | PASS | 2026-03-02 |
| 25 | lia-rdp | WINSV | 9025 | hex_respond | PASS | 2026-03-02 |
| 26 | lia-ldap | LDAP | 9026 | hex_respond | PASS | 2026-03-02 |
| 27 | lia-ipp | PRNT | 9027 | http | PASS | 2026-03-02 |
| 28 | lia-oracle | ORCL | 9028 | hex_respond | PASS | 2026-03-02 |
| 29 | lia-pjl-printer | PRNT | 9029 | tcp_respond | PASS | 2026-03-02 |
| 30 | lia-modbus | SCAD | 9030 | hex_respond | PASS | 2026-03-02 |
| 31 | lia-postgresql | PGSQL | 9031 | hex_respond | PASS | 2026-03-02 |
| 32 | lia-mysql | MYSQL | 9032 | tcp_init | PASS | 2026-03-02 |
| 33 | lia-mongodb | MONGO | 9033 | hex_respond | PASS | 2026-03-02 |
| 34 | lia-mariadb | MARD | 9034 | tcp_init | PASS | 2026-03-02 |
| 35 | lia-kibana | KIBAN | 9035 | http | PASS | 2026-03-02 |
| 36 | lia-prometheus | PROME | 9036 | http | PASS | 2026-03-02 |
| 37 | lia-traefik | TRAEF | 9037 | http | PASS | 2026-03-02 |
| 38 | lia-portainer | PORTA | 9038 | http | PASS | 2026-03-02 |
| 39 | lia-sonarqube | SONAR | 9039 | http | PASS | 2026-03-02 |
| 40 | lia-rabbitmq | RABBI | 9040 | http | PASS | 2026-03-02 |
| 41 | lia-mqtt | MQTT | 9041 | hex_respond | PASS | 2026-03-02 |
| 42 | lia-telnet | TELNT | 9042 | tcp_init | PASS | 2026-03-02 |
| 43 | lia-couchdb | COUCHDB | 9043 | http | PASS | 2026-03-02 |
| 44 | lia-cassandra | CASS | 9044 | hex_respond | PASS | 2026-03-02 |
| 45 | lia-vault | VAULT | 9045 | http | PASS | 2026-03-02 |
| 46 | lia-consul | CONSUL | 9046 | http | PASS | 2026-03-02 |
| 47 | lia-haproxy | HAPRO | 9047 | http | PASS | 2026-03-02 |
| 48 | lia-nexus | NEXUS | 9048 | http | PASS | 2026-03-02 |
| 49 | lia-gitea | GITEA | 9049 | http | PASS | 2026-03-02 |
| 50 | lia-tomcat | TOMC | 9050 | http | PASS | 2026-03-03 |
| 51 | lia-wildfly | WFLY | 9051 | http | PASS | 2026-03-03 |
| 52 | lia-glassfish | GLAS | 9052 | http | PASS | 2026-03-03 |
| 53 | lia-etcd | ETCD | 9053 | http | PASS | 2026-03-03 |
| 54 | lia-influxdb | INFL | 9054 | http | PASS | 2026-03-03 |
| 55 | lia-minio | MINI | 9055 | http | PASS | 2026-03-03 |
| 56 | lia-keycloak | KEYC | 9056 | http | PASS | 2026-03-03 |
| 57 | lia-nagios | NAGI | 9057 | http | PASS | 2026-03-03 |
| 58 | lia-activemq | ACTMQ | 9058 | http | PASS | 2026-03-03 |
| 59 | lia-phpmyadmin | PHPM | 9059 | http | PASS | 2026-03-03 |
| 60 | lia-adminer | ADMI | 9060 | http | PASS | 2026-03-03 |
| 61 | lia-mongo-express | MGEX | 9061 | http | PASS | 2026-03-03 |
| 62 | lia-jira | JIRA | 9062 | http | PASS | 2026-03-03 |
| 63 | lia-confluence | CONF | 9063 | http | PASS | 2026-03-03 |
| 64 | lia-spring-boot | SPRB | 9064 | http | PASS | 2026-03-03 |
| 65 | lia-gitlab | GITL | 9065 | http | PASS | 2026-03-03 |
| 66 | lia-artifactory | ARTF | 9066 | http | PASS | 2026-03-03 |
| 67 | lia-bitbucket | BITB | 9067 | http | PASS | 2026-03-03 |
| 68 | lia-nomad | NOMA | 9068 | http | PASS | 2026-03-03 |
| 69 | lia-neo4j | NEO4 | 9069 | http | PASS | 2026-03-03 |
| 70 | lia-awx | AWXT | 9070 | http | PASS | 2026-03-03 |
| 71 | lia-teamcity | TCIT | 9071 | http | PASS | 2026-03-03 |
| 72 | lia-splunk | SPLU | 9072 | http | PASS | 2026-03-03 |
| 73 | lia-graylog | GRAY | 9073 | http | PASS | 2026-03-03 |
| 74 | lia-opensearch | OPSE | 9074 | http | PASS | 2026-03-03 |
| 75 | lia-caddy | CADD | 9075 | http | PASS | 2026-03-03 |
| 76 | lia-envoy | ENVY | 9076 | http | PASS | 2026-03-03 |
| 77 | lia-kafka | KAFK | 9077 | hex_respond | PASS | 2026-03-03 |
| 78 | lia-zookeeper | ZOOK | 9078 | tcp_respond | PASS | 2026-03-03 |
| 79 | lia-clickhouse | CLKH | 9079 | http | PASS | 2026-03-03 |
| 80 | lia-argocd | ARCD | 9080 | http | PASS | 2026-03-03 |
| 81 | lia-harbor | HARB | 9081 | http | PASS | 2026-03-03 |
| 82 | lia-droneci | DRON | 9082 | http | PASS | 2026-03-03 |
| 83 | lia-jaeger | JAEG | 9083 | http | PASS | 2026-03-03 |
| 84 | lia-zipkin | ZIPK | 9084 | http | PASS | 2026-03-03 |
| 85 | lia-netdata | NETD | 9085 | http | PASS | 2026-03-03 |
| 86 | lia-sentry | SENT | 9086 | http | PASS | 2026-03-03 |
| 87 | lia-wazuh | WAZU | 9087 | http | PASS | 2026-03-03 |
| 88 | lia-fluentd | FLUE | 9088 | http | PASS | 2026-03-03 |
| 89 | lia-loki | LOKI | 9089 | http | PASS | 2026-03-03 |
| 90 | lia-tempo | TEMPO | 9090 | http | PASS | 2026-03-03 |
| 91 | lia-logstash | LOGST | 9091 | http | PASS | 2026-03-03 |
| 92 | lia-scylladb | SCLB | 9092 | http | PASS | 2026-03-03 |
| 93 | lia-cockroachdb | CRKR | 9093 | http | PASS | 2026-03-03 |
| 94 | lia-questdb | QSTD | 9094 | http | PASS | 2026-03-03 |
| 95 | lia-superset | SUPS | 9095 | http | PASS | 2026-03-03 |
| 96 | lia-airflow | AIRF | 9096 | http | PASS | 2026-03-03 |
| 97 | lia-metabase | MTBS | 9097 | http | PASS | 2026-03-03 |
| 98 | lia-alertmanager | ALMG | 9098 | http | PASS | 2026-03-03 |
| 99 | lia-thanos | THNS | 9099 | http | PASS | 2026-03-03 |
| 101 | lia-victoriametrics | VICM | 9101 | http | PASS | 2026-03-03 |
| 102 | lia-mimir | MIMR | 9102 | http | PASS | 2026-03-03 |
| 103 | lia-opentelemetry | OTEL | 9103 | http | PASS | 2026-03-03 |
| 104 | lia-redpanda | RDPD | 9104 | http | PASS | 2026-03-03 |
| 105 | lia-ksqldb | KSQL | 9105 | http | PASS | 2026-03-03 |
| 106 | lia-schema-registry | SREG | 9106 | http | PASS | 2026-03-03 |
| 107 | lia-meilisearch | MEIL | 9107 | http | PASS | 2026-03-03 |
| 108 | lia-weaviate | WEAV | 9108 | http | PASS | 2026-03-03 |
| 109 | lia-qdrant | QDRT | 9109 | http | PASS | 2026-03-03 |
| 110 | lia-zeppelin | ZPLN | 9110 | http | PASS | 2026-03-03 |

Score: 109/109 PASS (100%). Last recette: 2026-03-03.

## Taxonomy Naming Convention

Convention: 4-5 uppercase letters, intuitive product abbreviation.

### Round 1 (9050-9064)
TOMC (Tomcat), WFLY (WildFly), GLAS (GlassFish), ETCD (etcd), INFL (InfluxDB), MINI (MinIO), KEYC (Keycloak), NAGI (Nagios), ACTMQ (ActiveMQ), PHPM (phpMyAdmin), ADMI (Adminer), MGEX (Mongo Express), JIRA (Jira), CONF (Confluence), SPRB (Spring Boot)

### Round 2 (9065-9079)
GITL (GitLab), ARTF (Artifactory), BITB (Bitbucket), NOMA (Nomad), NEO4 (Neo4j), AWXT (AWX/Ansible Tower), TCIT (TeamCity), SPLU (Splunk), GRAY (Graylog), OPSE (OpenSearch), CADD (Caddy), ENVY (Envoy), KAFK (Kafka), ZOOK (Zookeeper), CLKH (ClickHouse)

### Round 3 (9080-9094)
ARCD (ArgoCD), HARB (Harbor), DRON (Drone CI), JAEG (Jaeger), ZIPK (Zipkin), NETD (Netdata), SENT (Sentry), WAZU (Wazuh), FLUE (Fluentd), LOKI (Grafana Loki), TEMPO (Grafana Tempo), LOGST (Logstash), SCLB (ScyllaDB), CRKR (CockroachDB), QSTD (QuestDB)

### Round 4 (9095-9110, skip 9100)
SUPS (Apache Superset), AIRF (Apache Airflow), MTBS (Metabase), ALMG (Alertmanager), THNS (Thanos), VICM (VictoriaMetrics), MIMR (Grafana Mimir), OTEL (OpenTelemetry Collector), RDPD (Redpanda), KSQL (ksqlDB), SREG (Schema Registry), MEIL (Meilisearch), WEAV (Weaviate), QDRT (Qdrant), ZPLN (Zeppelin)

## Navigation Commands

```bash
./banner_menu.sh list reseau
./banner_menu.sh list web
./banner_menu.sh list ics
./banner_menu.sh list databases
./banner_menu.sh list autre
```
