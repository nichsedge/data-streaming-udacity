from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, unbase64, split
from pyspark.sql.types import StructType, StructField, StringType, BooleanType, ArrayType, DoubleType

# Redis change schema (Kafka 'redis-server' topic schema)
redis_message_schema = StructType([
    StructField("key", StringType()),
    StructField("existType", StringType()),
    StructField("Ch", BooleanType()),
    StructField("Incr", BooleanType()),
    StructField("zSetEntries", ArrayType(
        StructType([
            StructField("element", StringType()),
            StructField("score", DoubleType())
        ])
    ))
])

# Customer JSON structure (decoded base64 from element)
customer_schema = StructType([
    StructField("customerName", StringType()),
    StructField("email", StringType()),
    StructField("phone", StringType()),
    StructField("birthDay", StringType())
])

# Create Spark application object
spark = SparkSession.builder \
    .appName("KafkaRedisCustomerStream") \
    .getOrCreate()

# Set log level to WARN
spark.sparkContext.setLogLevel('WARN')

# Read from Kafka topic 'redis-server'
redis_raw_stream_df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("subscribe", "redis-server") \
    .option("startingOffsets", "earliest") \
    .load()

# Cast the Kafka "value" field as string
redis_stream_df = redis_raw_stream_df.selectExpr("CAST(value AS STRING) as value")

# Parse the outer JSON structure from Redis topic
redis_json_df = redis_stream_df \
    .withColumn("redisData", from_json(col("value"), redis_message_schema)) \
    .select("redisData.*")

# Create a temporary view for SQL querying
redis_json_df.createOrReplaceTempView("RedisSortedSet")

# Use SQL to extract the base64 encoded customer JSON string
encoded_customer_df = spark.sql("""
    SELECT 
        zSetEntries[0].element as encodedCustomer
    FROM RedisSortedSet
    WHERE zSetEntries IS NOT NULL AND size(zSetEntries) > 0
""")

# Decode the base64 customer data to JSON string
decoded_customer_df = encoded_customer_df.withColumn("customer", unbase64(col("encodedCustomer")).cast("string"))

# Parse the decoded customer JSON into columns
customer_df = decoded_customer_df.withColumn("customerData", from_json(col("customer"), customer_schema)) \
    .select("customerData.*")

# Create a temp view for selecting specific fields
customer_df.createOrReplaceTempView("CustomerRecords")

# Select only records with non-null email and birthDay
email_and_birth_df = spark.sql("""
    SELECT 
        email,
        birthDay
    FROM CustomerRecords
    WHERE email IS NOT NULL AND birthDay IS NOT NULL
""")

# Extract birth year from birthDay
email_and_birth_year_df = email_and_birth_df \
    .withColumn("birthYear", split(col("birthDay"), "-").getItem(0)) \
    .select("email", "birthYear")

# Write the result to console
query = email_and_birth_year_df.writeStream \
    .outputMode("append") \
    .format("console") \
    .option("truncate", False) \
    .start()

query.awaitTermination()
