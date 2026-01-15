/**
 * @file service.h
 * @brief Base class for daemon services
 */

#pragma once

namespace cortexd {

/**
 * @brief Abstract base class for daemon services
 * 
 * All daemon services (IPC server, system monitor, etc.) should inherit
 * from this class to participate in the daemon lifecycle.
 */
class Service {
public:
    virtual ~Service() = default;
    
    /**
     * @brief Start the service
     * @return true if started successfully
     */
    virtual bool start() = 0;
    
    /**
     * @brief Stop the service
     */
    virtual void stop() = 0;
    
    /**
     * @brief Get service name for logging
     */
    virtual const char* name() const = 0;
    
    /**
     * @brief Get service priority (higher = start earlier)
     */
    virtual int priority() const { return 0; }
    
    /**
     * @brief Check if service is currently running
     */
    virtual bool is_running() const = 0;
    
    /**
     * @brief Check if service is healthy
     */
    virtual bool is_healthy() const { return is_running(); }
};

} // namespace cortexd
