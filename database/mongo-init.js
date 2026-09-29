// get info from environment variables
const db_name = process.env.MONGO_DATABASE_NAME;
const collection_name = process.env.MONGO_COLLECTION_NAME;
const app_username = process.env.MONGO_APP_USERNAME;
const app_password = process.env.MONGO_APP_PASSWORD;

const mydb = db.getSiblingDB(db_name)

// create the collection with validation and indexes
mydb.createCollection(collection_name, {
    validator: {
        $jsonSchema: {
            bsonType: "object",
            required: ["original_url", "shortened_path", "expires_at"],
            properties: {
                original_url: { bsonType: "string", description: "original full URL" },
                shortened_path: { bsonType: "string", description: "shortened path fot the short URL" },
                expires_at: { bsonType: "date", description: "date of expiration" }
            }
        }
    }
});
const mycollection = mydb.getCollection(collection_name);
mycollection.createIndex({ original_url: 1 }, { unique: true });
mycollection.createIndex({ shortened_path: 1 }, { unique: true });
mycollection.createIndex({ expires_at: 1 }, { expireAfterSeconds: 0 });

// create database user
mydb.createUser({
    user: process.env.MONGO_APP_USERNAME,
    pwd: process.env.MONGO_APP_PASSWORD,
    roles: [{ role: "readWrite", db: db_name }]
});
