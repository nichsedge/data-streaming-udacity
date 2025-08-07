from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, unbase64, split, to_json, struct
from pyspark.sql.types import StructField, StructType, StringType, BooleanType, ArrayType, DoubleType

# Schema for redis-server Kafka topic
redis_schema = StructType([
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

# Schema for the customer JSON (base64 decoded)
customer_schema = StructType([
    StructField("customerName", StringType()),
    StructField("email", StringType()),
    StructField("phone", StringType()),
    StructField("birthDay", StringType())
])

# Schema for the stedi-events Kafka topic
risk_schema = StructType([
    StructField("customer", StringType()),
    StructField("score", StringType()),
    StructField("riskDate", StringType())
])

# Create Spark session
spark = SparkSession.builder.appName("KafkaJoinStream").getOrCreate()
spark.sparkContext.setLogLevel("WARN")

# Read redis-server topic (customer data)
redis_raw_df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("subscribe", "redis-server") \
    .option("startingOffsets", "earliest") \
    .load()

redis_df = redis_raw_df.selectExpr("CAST(value AS STRING) as value")

# Parse the outer Redis JSON
parsed_redis_df = redis_df.withColumn("data", from_json(col("value"), redis_schema)).select("data.*")

# Select base64-encoded customer element
encoded_customer_df = parsed_redis_df \
    .filter("zSetEntries IS NOT NULL AND size(zSetEntries) > 0") \
    .selectExpr("zSetEntries[0].element as encodedCustomer")

# Decode base64 to customer JSON
decoded_customer_df = encoded_customer_df \
    .withColumn("customer", unbase64(col("encodedCustomer")).cast("string")) \
    .withColumn("customerData", from_json(col("customer"), customer_schema)) \
    .select("customerData.*")

# Extract email and birth year
email_birth_year_df = decoded_customer_df \
    .withColumn("birthYear", split(col("birthDay"), "-").getItem(0)) \
    .select("email", "birthYear")

# Read stedi-events topic (risk scores)
risk_raw_df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("subscribe", "stedi-events") \
    .option("startingOffsets", "earliest") \
    .load()

risk_df = risk_raw_df.selectExpr("CAST(value AS STRING) as value") \
    .withColumn("riskData", from_json(col("value"), risk_schema)) \
    .select("riskData.*")

# Join on email = customer
joined_df = risk_df.join(email_birth_year_df, risk_df.customer == email_birth_year_df.email)

# Format as JSON structure
output_df = joined_df.select(
    col("customer"),
    col("score"),
    col("email"),
    col("birthYear")
).withColumn("value", to_json(struct("customer", "score", "email", "birthYear")))

# Write to new Kafka topic: customer-risk
output_df.selectExpr("CAST(value AS STRING)") \
    .writeStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("topic", "customer-risk") \
    .option("checkpointLocation", "/tmp/kafka_join_checkpoint") \
    .outputMode("append") \
    .start() \
    .awaitTermination()
