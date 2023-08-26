# 通过 OpenDAL 集成存储的配置方法

## 需要配置的参数

```dotenv
file_storage=opendal
opendal_scheme=<service_name>
opendal_<service_name>_<service_setting>=...
```

以 Gcs 为例，需要配置的参数如下：
```dotenv
file_storage=opendal
opendal_scheme=gcs
opendal_gcs_root=<root>
opendal_gcs_bucket=<bucket_name>
opendal_gcs_credential=<base64_credential>
```

所有支持的服务可以在[此处](https://opendal.apache.org/docs/rust/opendal/services/index.html)查看。
具体服务的配置参数与 OpenDAL 文档一致。

## 补充说明

通过 OpenDAL 集成的服务均通过服务器中转下载。因此，每次下载既消耗存储服务的流量，也消耗服务器的流量。

OpenDAL 和该项目本身都支持本地存储、`s3`、`onedrive`。不同之处有以下几点:
1. 项目的支持通过预签名实现，不消耗服务器流量。而 OpenDAL 通过服务器中转下载，消耗服务器流量。（本地存储除外）
2. 项目的支持对于异常情况可能会有更多的调试信息，方便排查问题。
3. OpenDAL 项目本身采用 Rust 编写，性能更好。