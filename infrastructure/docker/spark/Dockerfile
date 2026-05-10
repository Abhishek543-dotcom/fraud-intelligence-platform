# ============================================================
# Spark — Dockerfile with Iceberg, Hadoop-AWS, and Python deps
# Base: bitnami/spark:3.5 (ARM64 compatible)
# ============================================================
FROM bitnami/spark:3.5

USER root

# Iceberg and AWS JARs for S3/MinIO connectivity
ENV ICEBERG_VERSION=1.5.0
ENV SPARK_VERSION=3.5
ENV SCALA_VERSION=2.12
ENV HADOOP_AWS_VERSION=3.3.4
ENV AWS_SDK_VERSION=1.12.262

RUN curl -fSL "https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-${SPARK_VERSION}_${SCALA_VERSION}/${ICEBERG_VERSION}/iceberg-spark-runtime-${SPARK_VERSION}_${SCALA_VERSION}-${ICEBERG_VERSION}.jar" \
      -o /opt/bitnami/spark/jars/iceberg-spark-runtime.jar && \
    curl -fSL "https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-aws-bundle/${ICEBERG_VERSION}/iceberg-aws-bundle-${ICEBERG_VERSION}.jar" \
      -o /opt/bitnami/spark/jars/iceberg-aws-bundle.jar && \
    curl -fSL "https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/${HADOOP_AWS_VERSION}/hadoop-aws-${HADOOP_AWS_VERSION}.jar" \
      -o /opt/bitnami/spark/jars/hadoop-aws.jar && \
    curl -fSL "https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/${AWS_SDK_VERSION}/aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar" \
      -o /opt/bitnami/spark/jars/aws-java-sdk-bundle.jar

# Install Python packages
RUN pip install --no-cache-dir \
    pyspark==${SPARK_VERSION}.0 \
    kafka-python==2.0.2 \
    pandas==2.1.4 \
    pyarrow==14.0.2 \
    boto3==1.34.0 \
    requests==2.31.0

# Spark defaults for Iceberg + S3/MinIO
RUN cat >> /opt/bitnami/spark/conf/spark-defaults.conf <<'EOF'
spark.sql.extensions                           org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions
spark.sql.catalog.nessie                       org.apache.iceberg.spark.SparkCatalog
spark.sql.catalog.nessie.catalog-impl          org.apache.iceberg.nessie.NessieCatalog
spark.sql.catalog.nessie.uri                   http://nessie:19120/api/v1
spark.sql.catalog.nessie.ref                   main
spark.sql.catalog.nessie.warehouse             s3a://lakehouse/warehouse
spark.sql.catalog.nessie.io-impl              org.apache.iceberg.aws.s3.S3FileIO
spark.hadoop.fs.s3a.endpoint                   http://minio:9000
spark.hadoop.fs.s3a.access.key                 minioadmin
spark.hadoop.fs.s3a.secret.key                 minioadmin123
spark.hadoop.fs.s3a.path.style.access          true
spark.hadoop.fs.s3a.impl                       org.apache.hadoop.fs.s3a.S3AFileSystem
spark.sql.defaultCatalog                       nessie
spark.serializer                               org.apache.spark.serializer.KryoSerializer
spark.sql.adaptive.enabled                     true
spark.sql.adaptive.coalescePartitions.enabled   true
EOF

USER 1001
