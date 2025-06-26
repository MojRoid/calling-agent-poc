import winston from 'winston';
import * as fs from 'fs';
import * as path from 'path';

// Create logs directory if it doesn't exist
const logsDir = path.join(process.cwd(), 'logs');
if (!fs.existsSync(logsDir)) {
  fs.mkdirSync(logsDir, { recursive: true });
}

// Create timestamped log file
const timestamp = new Date().toISOString().replace(/[:.]/g, '-').substring(0, 19);
const logFile = path.join(logsDir, `calling_agent_${timestamp}.log`);

// Define custom log format
const customFormat = winston.format.printf(({ level, message, timestamp, service, ...meta }) => {
  const metaStr = Object.keys(meta).length ? ` ${JSON.stringify(meta)}` : '';
  return `${timestamp} - ${service || 'app'} - ${level.toUpperCase()} - ${message}${metaStr}`;
});

// Create the logger
const logger = winston.createLogger({
  level: 'info',
  format: winston.format.combine(
    winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
    winston.format.errors({ stack: true }),
    customFormat
  ),
  transports: [
    // File transport
    new winston.transports.File({ 
      filename: logFile,
      level: 'info'
    }),
    // Console transport
    new winston.transports.Console({
      format: winston.format.combine(
        winston.format.colorize(),
        customFormat
      )
    })
  ]
});

// Create logger factory for different modules
export function createLogger(service: string): winston.Logger {
  return logger.child({ service });
}

// Log the startup
logger.info(`Logging configured. Log file: ${logFile}`);

export default logger; 